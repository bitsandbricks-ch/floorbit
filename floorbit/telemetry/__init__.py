"""Device telemetry: switches, routers and firewalls report to Floorbit without LibreNMS
(docs/telemetry.md).

The pieces:

- ``targets``: the devices and how to collect from each (Settings > Telemetry), secrets sealed.
- ``telegraf``: Telegraf's config made from them. Telegraf polls SNMP, takes traps, subscribes to
  gNMI and takes Cisco MDT dial-out, and sends line protocol to the collector.
- ``pollers``: the API drivers Telegraf doesn't have (NX-API, RESTCONF, OPNsense).
- ``state``: the latest picture of each device, answered by the telemetry monitoring plugin.
- ``storage``: series over time, in VictoriaMetrics or (lite) Floorbit's own database.

**Where it runs.** Self-hosted, Floorbit is the collector: the Telegraf sidecar posts to
``/api/telemetry/write`` and the pollers run here. Hosted, with a local agent enrolled, the agent is
the collector: the telemetry plugin's agent part (builtin_plugins/telemetry/agent.py) gets the
targets as its settings, writes Telegraf's config, keeps the picture itself (monitoring calls
reach it through the link) and sends the hosted side only the normalised series.
"""
import os
import threading
import time

from . import lineproto, pollers, targets, telegraf
from . import state as state_mod
from . import storage as storage_mod

CONF_ENV = 'FLOORBIT_TELEGRAF_CONF'
OUTPUT_ENV = 'FLOORBIT_TELEGRAF_OUTPUT'
POLL_EVERY = 60
MAX_BODY = 32 * 1024 * 1024

_runner = None


def ingest(text, now=None):
    """A batch of line protocol from Telegraf. Returns {taken, points, bad}."""
    points, bad = lineproto.parse(text)
    taken = state_mod.state.apply(points, now)
    storage_mod.storage().forward_raw(points)
    return {'taken': taken, 'points': len(points), 'bad': bad}


def collector_here():
    """Is this Floorbit the collector? Not while a local agent collects for it."""
    from .. import agent_link
    return not agent_link.active()


def conf_path():
    from .. import store
    return os.environ.get(CONF_ENV) or store.tenant_path('telegraf', 'telegraf.conf')


def render_here(target_list=None):
    """Telegraf's config for the sidecar next to this Floorbit."""
    target_list = ([targets.opened(t) for t in target_list] if target_list is not None
                   else targets.all_opened())
    output = os.environ.get(OUTPUT_ENV) or 'http://floorbit:5000/api/telemetry/write'
    return telegraf.render(target_list, output, targets.ingest_token())


def write_conf(text=None):
    """Write telegraf.conf where the sidecar reads it (it reloads on change). Only when it changed,
    so Telegraf doesn't restart its polls for nothing. Returns True when it wrote."""
    text = render_here() if text is None else text
    path = conf_path()
    try:
        with open(path, encoding='utf-8') as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    tmp = path + '.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)
    return True


class Runner:
    """The collector's background work here: pollers, the snapshot to storage, telegraf.conf."""

    def __init__(self, log=print):
        self.log = log
        self._stop = threading.Event()
        self.poll_errors = {}
        self.last_poll = None
        self.blocks = None

    def once(self, now=None):
        now = time.time() if now is None else now
        from ..database import DatabaseUnavailable
        try:
            every = targets.all_opened()
        except DatabaseUnavailable:
            every = None
        if every is not None:
            state_mod.state.know(every)
            if collector_here():
                with_secrets = [t for t in every if set(t['drivers']) & set(pollers.POLLERS)]
                found, self.poll_errors = pollers.poll_all(with_secrets, now, log=self.log, blocks=self._blocks())
                state_mod.state.apply(found, now)
                storage_mod.storage().forward_raw(found)
                self.last_poll = now
                try:
                    write_conf()
                except OSError as exc:
                    self.log(f'[telemetry] cannot write {conf_path()}: {exc}')
        if collector_here() and state_mod.state.devices:
            storage_mod.storage().sample(storage_mod.snapshot(now=now), now)
            self.record_endpoints(now)

    def record_endpoints(self, now):
        """Where each machine is, into the IP/MAC history (floorbit/endpoints.py)."""
        from .. import endpoints, sources
        from . import clients
        registry = sources.registry
        spec = registry.specs.get('telemetry') if registry is not None else None
        if spec is None or not registry.enabled(spec):
            return
        settings = registry.settings_of(spec)
        endpoints.history().record(clients.sightings(state_mod.state, settings.get('uplink_macs') or 8,
                                                     settings.get('exclude') or ()), now)

    def _blocks(self):
        """Refused logins, kept next to the state so a restart doesn't try them again either."""
        if self.blocks is None:
            from .. import store
            from ..plugins.agent import AuthBlocks

            class Blocks(AuthBlocks):
                def auth_failed(blocks, device, credential, rev=None, message=''):
                    if blocks.failed(device, credential, rev, message):
                        self.log(f'[telemetry] {message}: not trying {device} again until its login is changed')
                        # An inventory login: blocked on the device too, where a tech clears it.
                        from .. import inventory_scope
                        try:
                            inventory_scope.auth_failed(device, credential, rev, 'telemetry', message)
                        except Exception as exc:  # noqa: BLE001
                            self.log(f'[telemetry] could not keep the block on {device}: {exc}')

            self.blocks = Blocks(store.tenant_path('telemetry-logins.json'))
        return self.blocks

    def loop(self):
        while not self._stop.wait(POLL_EVERY if self.last_poll else 5):
            try:
                self.once()
            except Exception as exc:  # noqa: BLE001  # a bad round must not end the collector
                self.log(f'[telemetry] {type(exc).__name__}: {exc}')

    def stop(self):
        self._stop.set()


def start(log=print):
    global _runner
    if _runner is None:
        _runner = Runner(log)
        threading.Thread(target=_runner.loop, name='telemetry', daemon=True).start()
    return _runner


def status():
    from .. import agent_link
    return {'collector': 'here' if collector_here() else 'agent', 'agents': agent_link.active(),
            'devices': len(state_mod.state.devices), 'points': state_mod.state.points,
            'unknown': state_mod.state.unknown, 'storage': storage_mod.storage().status(),
            'poll_errors': dict(_runner.poll_errors) if _runner else {},
            'conf_path': conf_path() if collector_here() else None}


def init_app(app, start_background=True):
    """The collector's background work starts with the first request, like the other watchers."""
    started = threading.Event()

    @app.before_request
    def start_telemetry_once():
        if start_background and not started.is_set():
            started.set()
            start()
