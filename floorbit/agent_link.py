"""The hosted side of the local agent (issue #2). See docs/agent.md.

A hosted Floorbit can't reach the event network: LibreNMS and NetBox sit behind the event's
firewall. A small agent runs there instead and opens the connection itself. It asks this instance
for work (a long poll), runs each call against the event's own sources and posts the answers back.
Nothing on the event network has to be reachable from outside.

- **Credentials:** an admin enrols an agent and gets its key once (``fba_<id>_<secret>``); only a
  hash is kept, in data.json under ``agents``. Revoking it stops the agent at its next request.
- **Calls:** ``Tunnel.call()`` queues a monitoring call and waits for the answer. While no agent
  has asked for work recently, a call fails at once, and the monitoring source answers from its
  last good data, marked stale (floorbit/sources/lastgood.py).
- **The source:** with an agent enrolled, ``AgentMonitoring`` is what ``sources.monitoring()``
  returns, so the floor plan, status monitor and check-in page work as with a local LibreNMS.
- **The inventory:** an inventory sync also asks the agent for its inventory plugins' devices
  (``inventory_feeds``), merged under each plugin's own id (floorbit/blueprints/inventory.py),
  and a cable import for their cables (``cable_feeds``, floorbit/cables.py).

One app process (gunicorn runs one worker), so the queue lives in memory.
"""
import collections
import hashlib
import hmac
import itertools
import os
import re
import secrets
import threading
import time

from .store import load_data, save_data

KEY = 'agents'
PREFIX = 'fba_'
MAX_AGENTS = 10
NAME_RE = re.compile(r'^[^\x00-\x1f<>]{1,60}$')
KEY_RE = re.compile(r'^fba_([0-9a-f]{8})_([A-Za-z0-9_-]{20,80})$')
CONNECTED_FOR = 60       # an agent that asked for work this recently counts as connected
CALL_TIMEOUT = 8         # seconds a page waits for the agent's answer
MAX_WAIT = 25            # longest long poll, under the usual 30 s proxy timeouts
MAX_PENDING = 200        # calls queued for the agent; more fail at once
TOUCH_EVERY = 30         # seconds between "last seen" writes to data.json
INVENTORY_TIMEOUT = 25   # a NetBox sync pages through every device: give it longer, under proxy timeouts
# What the agent may be asked: the monitoring source's methods (floorbit/sources) and the
# inventory feeds of its inventory plugins (NetBox), nothing else.
METHODS = ('configured', 'devices', 'device_details', 'resolve_ip', 'port_stats', 'device_ports', 'arp',
           'inventory_feeds', 'cable_feeds')
PLUGIN_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_.-]{0,59}$')

_lock = threading.Lock()
_active = None            # ((data file, mtime), is an agent enrolled?)


class AgentError(ValueError):
    status = 400


class AgentUnavailable(RuntimeError):
    """No agent is connected, or it didn't answer in time."""


def _hash(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def _public(a, now):
    seen = a.get('last_seen')
    return {'id': a['id'], 'name': a['name'], 'created_at': a['created_at'], 'created_by': a.get('created_by'),
            'last_seen': seen, 'version': a.get('version'), 'address': a.get('address'),
            'connected': bool(seen and now - seen < CONNECTED_FOR)}


def all_agents(data=None, now=None):
    data = load_data() if data is None else data
    now = time.time() if now is None else now
    return [{**_public(a, now), 'stats': tunnel.stats(a['id'], now)} for a in data.get(KEY) or []]


def active():
    """Is an agent enrolled? Every monitoring call asks, so the answer is kept until data.json changes."""
    global _active
    from . import store
    try:
        stamp = (store.DATA_FILE, os.stat(store.DATA_FILE).st_mtime_ns)
    except OSError:
        return False
    if _active is None or _active[0] != stamp:
        _active = (stamp, bool(load_data().get(KEY)))
    return _active[1]


def _forget_cache():
    global _active
    _active = None


def enrol(name, by, now=None):
    """A new agent. Returns (its record, the key): the key is shown this once."""
    name = str(name or '').strip()
    if not NAME_RE.match(name):
        raise AgentError('Give the agent a name of up to 60 characters, such as the event or the site.')
    now = time.time() if now is None else now
    with _lock:
        data = load_data()
        agents = data.setdefault(KEY, [])
        if len(agents) >= MAX_AGENTS:
            raise AgentError(f'At most {MAX_AGENTS} agents. Revoke one you no longer use.')
        agent_id = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        record = {'id': agent_id, 'name': name, 'hash': _hash(secret), 'created_at': now, 'created_by': by,
                  'last_seen': None, 'version': None, 'address': None}
        agents.append(record)
        save_data(data)
    _forget_cache()
    return _public(record, now), f'{PREFIX}{agent_id}_{secret}'


def revoke(agent_id):
    with _lock:
        data = load_data()
        agents = data.get(KEY) or []
        found = next((a for a in agents if a['id'] == agent_id), None)
        if not found:
            err = AgentError('No such agent.')
            err.status = 404
            raise err
        data[KEY] = [a for a in agents if a['id'] != agent_id]
        save_data(data)
    _forget_cache()
    return found['name']


def check(key, version=None, address=None, now=None):
    """The agent a key belongs to, or None. Notes when it was last seen (now and then)."""
    m = KEY_RE.match(str(key or '').strip())
    if not m:
        return None
    now = time.time() if now is None else now
    agent_id, secret = m.groups()
    data = load_data()
    found = next((a for a in data.get(KEY) or [] if a['id'] == agent_id), None)
    if not found or not hmac.compare_digest(found['hash'], _hash(secret)):
        return None
    tunnel.seen(now)
    if not found.get('last_seen') or now - found['last_seen'] >= TOUCH_EVERY or found.get('version') != version:
        with _lock:
            data = load_data()
            for a in data.get(KEY) or []:
                if a['id'] == agent_id:
                    a.update(last_seen=now, version=(str(version)[:40] if version else None),
                             address=(str(address)[:64] if address else None))
            save_data(data)
    return {'id': found['id'], 'name': found['name']}


# ── The call tunnel ────────────────────────────────────────────────────────────────────────────

STATS_WINDOW = 3600      # the Local agents page shows the last hour's calls
STATS_KEEP = 5000        # answers kept per agent for that, at most


class _Call:
    __slots__ = ('agent', 'args', 'done', 'error', 'id', 'method', 'ok', 'result', 'taken', 'taken_at')

    def __init__(self, call_id, method, args):
        self.id, self.method, self.args = call_id, method, args
        self.done = threading.Event()
        self.ok, self.result, self.error, self.taken = False, None, None, False
        self.agent, self.taken_at = None, None


class Tunnel:
    def __init__(self):
        self._cond = threading.Condition()
        self._pending = collections.deque()
        self._calls = {}
        self._ids = itertools.count(1)
        self._stats = {}          # agent id -> deque of (when, ms, ok, method, error)
        self.last_seen = None

    def reset(self):
        with self._cond:
            self._pending.clear()
            self._calls.clear()
            self._stats.clear()
            self.last_seen = None

    def seen(self, now=None):
        self.last_seen = time.time() if now is None else now

    def connected(self, now=None):
        now = time.time() if now is None else now
        return self.last_seen is not None and now - self.last_seen < CONNECTED_FOR

    def call(self, method, args=(), timeout=CALL_TIMEOUT):
        """Ask the agent; returns its answer. Raises AgentUnavailable, or AgentError with its error."""
        if method not in METHODS:
            raise AgentError(f'{method} is not something the agent answers.')
        if not self.connected():
            raise AgentUnavailable('The local agent is not connected.')
        with self._cond:
            if len(self._pending) >= MAX_PENDING:
                raise AgentUnavailable('The local agent has too much to do.')
            call = _Call(str(next(self._ids)), method, list(args))
            self._calls[call.id] = call
            self._pending.append(call)
            self._cond.notify_all()
        try:
            if not call.done.wait(timeout):
                raise AgentUnavailable(f'The local agent did not answer {method} within {timeout} s.')
        finally:
            with self._cond:
                self._calls.pop(call.id, None)
                if call in self._pending:
                    self._pending.remove(call)
        if not call.ok:
            raise AgentError(call.error or f'{method} failed on the agent.')
        return call.result

    def take(self, wait=MAX_WAIT, limit=20, agent=None):
        """The calls waiting for the agent, waiting up to ``wait`` seconds for the first one."""
        deadline = time.monotonic() + max(0.0, min(float(wait), MAX_WAIT))
        with self._cond:
            while not self._pending:
                left = deadline - time.monotonic()
                if left <= 0:
                    return []
                self._cond.wait(left)
            out = []
            while self._pending and len(out) < limit:
                call = self._pending.popleft()
                call.taken, call.agent, call.taken_at = True, agent, time.monotonic()
                out.append({'id': call.id, 'method': call.method, 'args': call.args})
            return out

    def answer(self, call_id, ok, result=None, error=None):
        """The agent's answer to one call. False when nobody waits for it any more."""
        with self._cond:
            call = self._calls.get(str(call_id))
        if call is None:
            return False
        call.ok, call.result, call.error = bool(ok), result, (str(error)[:300] if error else None)
        call.done.set()
        if call.agent is not None and call.taken_at is not None:
            ms = (time.monotonic() - call.taken_at) * 1000
            with self._cond:
                log = self._stats.setdefault(call.agent, collections.deque(maxlen=STATS_KEEP))
                log.append((time.time(), ms, call.ok, call.method, call.error))
        return True

    def stats(self, agent, now=None):
        """The last hour of one agent's answers: how many, how many failed, the median time, the
        last error. Kept in memory only, so a restart starts over."""
        now = time.time() if now is None else now
        with self._cond:
            recent = [r for r in self._stats.get(agent) or () if now - r[0] < STATS_WINDOW]
        if not recent:
            return {'calls': 0, 'failed': 0, 'median_ms': None, 'last_error': None}
        times = sorted(r[1] for r in recent)
        failed = [r for r in recent if not r[2]]
        last = failed[-1] if failed else None
        return {'calls': len(recent), 'failed': len(failed), 'median_ms': round(times[len(times) // 2]),
                'last_error': {'at': last[0], 'method': last[3], 'error': last[4]} if last else None}


tunnel = Tunnel()


def inventory_feeds():
    """The agent's inventory plugins and their devices: ``[{plugin, name, items | error}]``."""
    return feeds('inventory_feeds')


def cable_feeds():
    """The agent's plugins that know cables (NetBox) and their cables, as ``inventory_feeds``."""
    return feeds('cable_feeds')


def feeds(method):
    """``[{plugin, name, items | error}]`` from the agent. Raises AgentUnavailable or AgentError.
    Feeds that don't look right are dropped."""
    feeds = tunnel.call(method, timeout=INVENTORY_TIMEOUT)
    out = []
    for f in feeds if isinstance(feeds, list) else []:
        if not isinstance(f, dict) or not PLUGIN_ID_RE.match(str(f.get('plugin') or '')):
            continue
        name = str(f.get('name') or f['plugin'])[:60]
        if f.get('error') or not isinstance(f.get('items'), list):
            out.append({'plugin': f['plugin'], 'name': name, 'error': str(f.get('error') or 'no devices sent')[:300]})
        else:
            out.append({'plugin': f['plugin'], 'name': name, 'items': f['items']})
    return out


# ── The monitoring source it feeds ─────────────────────────────────────────────────────────────

def monitoring_source():
    """The agent-fed monitoring source (floorbit/sources), made here to keep the import late."""
    from .plugins.base import PluginError
    from .sources import PluginMonitoring

    class AgentMonitoring(PluginMonitoring):
        """``sources.monitoring()`` while an agent is enrolled: every call goes through the tunnel.
        A failed or unanswered call is a PluginError, so the last good answer is used, marked stale."""

        def __init__(self):   # no registry or plugin spec: the plugin runs on the agent
            self.name = 'agent'
            self.label = 'Local agent'

        def _call(self, method, *args):
            try:
                return tunnel.call(method, args)
            except (AgentUnavailable, AgentError) as exc:
                raise PluginError(str(exc)) from None

        def enabled(self):
            return True

        def device_ports(self, hostname):
            from . import sources
            if sources.offline():
                return []
            try:
                return self._call('device_ports', hostname) or []
            except PluginError as exc:
                print(f'[agent] device_ports failed: {exc}')
                return []

    return AgentMonitoring()
