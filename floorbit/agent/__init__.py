"""The local agent for a hosted Floorbit (issue #2). See docs/agent.md.

It runs on the event network, in the same image as Floorbit (``python -m floorbit.agent``), with the
event's own monitoring plugin set up the usual way (``LIBRENMS_URL`` and ``LIBRENMS_TOKEN``, or any
other monitoring plugin). It connects out to the hosted Floorbit (``FLOORBIT_URL``) with its key
(``FLOORBIT_AGENT_KEY``), asks for calls in a long poll, runs each one against the local plugin and
posts the answer back. The hosted side is floorbit/agent_link.py.

Nothing listens here: the agent only makes outgoing HTTPS requests. When the hosted Floorbit can't
be reached it waits and tries again, a little longer each time (up to ``MAX_BACKOFF``).
"""
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

KEY_HEADER = 'Floorbit-Agent-Key'
VERSION_HEADER = 'Floorbit-Agent-Version'
POLL_WAIT = 25            # the hosted side holds a poll at most this long
HTTP_TIMEOUT = 40         # a bit more than a poll
MAX_BACKOFF = 60
WORKERS = 4               # calls run side by side: one slow port lookup mustn't hold up the rest
METHODS = ('configured', 'devices', 'device_details', 'resolve_ip', 'port_stats', 'device_ports', 'arp')


class Refused(RuntimeError):
    """The hosted Floorbit refused the key: retrying won't help."""


def local_executor(app):
    """Run a call against this machine's monitoring plugin, as the hosted Floorbit would locally."""
    def execute(method, args):
        from .. import sources
        from ..plugins.base import PluginError
        if method not in METHODS:
            raise PluginError(f'{method} is not something the agent answers')
        with app.app_context():
            registry = sources.registry
            spec = registry.monitoring_source() if registry is not None else None
            if spec is None:
                raise PluginError('No monitoring plugin is set up on the agent (LIBRENMS_URL and LIBRENMS_TOKEN?)')
            return registry.call(spec, method, *args)
    return execute


class Agent:
    def __init__(self, url, key, execute, http=None, version='0', log=print):
        import requests
        self.url = url.rstrip('/')
        self.key = key
        self.execute = execute
        self.http = http or requests.Session()
        self.version = version
        self.log = log
        self._pool = ThreadPoolExecutor(WORKERS)
        self._stop = threading.Event()
        self.answered = 0
        self.poll_wait = POLL_WAIT

    def _headers(self, json_body=False):
        h = {KEY_HEADER: self.key, VERSION_HEADER: self.version}
        if json_body:
            h['Content-Type'] = 'application/json'
        return h

    def _check(self, resp):
        if resp.status_code == 401:
            raise Refused('The hosted Floorbit refused the agent key: it is wrong or was revoked. '
                          'Enrol the agent again.')
        resp.raise_for_status()
        return resp.json()

    def hello(self):
        return self._check(self.http.get(f'{self.url}/api/agent/v1/hello', headers=self._headers(),
                                         timeout=HTTP_TIMEOUT))

    def poll(self, wait=POLL_WAIT):
        """One long poll; runs the calls it brings. Returns how many it got."""
        body = self._check(self.http.get(f'{self.url}/api/agent/v1/calls', params={'wait': wait},
                                         headers=self._headers(), timeout=HTTP_TIMEOUT))
        calls = body.get('calls') or []
        for call in calls:
            self._pool.submit(self._run, call)
        return len(calls)

    def _run(self, call):
        try:
            result = self.execute(call['method'], call.get('args') or [])
            answer = {'id': call['id'], 'ok': True, 'result': result}
        except Exception as exc:  # noqa: BLE001  # the hosted side gets the message, the agent goes on
            answer = {'id': call['id'], 'ok': False, 'error': str(exc)[:300] or type(exc).__name__}
        # default=str: a plugin answer may hold dates or other things JSON doesn't know.
        payload = json.dumps({'answers': [answer]}, default=str)
        try:
            self._check(self.http.post(f'{self.url}/api/agent/v1/answers', data=payload,
                                       headers=self._headers(True), timeout=HTTP_TIMEOUT))
            self.answered += 1
        except Exception as exc:  # noqa: BLE001  # the call times out on the hosted side; nothing to keep
            self.log(f'[agent] could not send the answer to {call["method"]}: {exc}')

    def stop(self):
        self._stop.set()

    def run(self):
        """Poll until stopped. Raises Refused when the key is no good."""
        backoff, connected = 1, False
        while not self._stop.is_set():
            try:
                if not connected:
                    hello = self.hello()
                    self.log(f'[agent] connected to {self.url} as "{hello["name"]}" '
                             f'(Floorbit {hello.get("server_version")})')
                    connected, backoff = True, 1
                self.poll(self.poll_wait)
            except Refused:
                raise
            except Exception as exc:  # noqa: BLE001  # network trouble: wait and try again
                if connected:
                    self.log(f'[agent] lost the connection to {self.url}: {exc}')
                else:
                    self.log(f'[agent] cannot reach {self.url} ({exc}); trying again in {backoff} s')
                connected = False
                self._stop.wait(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)


def main(argv=None):
    url = os.environ.get('FLOORBIT_URL', '').strip()
    key = os.environ.get('FLOORBIT_AGENT_KEY', '').strip()
    if not url or not key:
        print('Set FLOORBIT_URL (the hosted Floorbit) and FLOORBIT_AGENT_KEY (from Settings > Local agents).',
              file=sys.stderr)
        return 2
    if not url.startswith('https://') and os.environ.get('FLOORBIT_AGENT_INSECURE') != '1':
        print('FLOORBIT_URL must start with https://: the key and the event data go over it. '
              'For a test on a trusted network, set FLOORBIT_AGENT_INSECURE=1.', file=sys.stderr)
        return 2
    # The agent keeps no floor plan: its settings file is its own, next to nothing else.
    os.environ.setdefault('FLOORBIT_DATA_FILE', os.path.abspath('agent-data.json'))
    from .. import ROOT, create_app
    app = create_app(start_background=False)
    version_file = ROOT / 'VERSION'
    version = version_file.read_text().strip() if version_file.is_file() else '0'
    agent = Agent(url, key, local_executor(app), version=version)
    try:
        agent.run()
    except Refused as exc:
        print(f'[agent] {exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        agent.stop()
    return 0
