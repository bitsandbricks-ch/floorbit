"""The service health wall (issue #28): DHCP, DNS, the LAN cache, game servers and the uplink,
each green (up), amber (warn) or red (down). See docs/health.md.

Floorbit checks nothing itself: every check comes from a plugin with ``uses: [health]`` whose
``health_checks()`` returns a list like::

    [{"id": "dhcp-players", "name": "DHCP players", "kind": "dhcp", "status": "warn",
      "summary": "38 leases left", "link": "/dashboard",
      "metrics": [{"label": "Leases left", "value": 38, "unit": "", "tone": "warn"}]}]

The checks are data, cleaned here like widgets (text stays text, links stay on this site). A
background thread asks every health plugin each ``HEALTH_INTERVAL`` seconds. A new status counts
once it was seen ``HEALTH_CONFIRM`` polls in a row, so one slow answer pages nobody; then it
publishes ``health.changed`` (the wall, Discord alerts and plugin hooks listen). The first poll
only records a baseline, like the switch status monitor.
"""
import threading
import time

from integrations import config, events

from . import features, game_servers
from .plugins import PluginError

KINDS = ('dhcp', 'dns', 'cache', 'game', 'uplink', 'web', 'other')
STATES = ('up', 'warn', 'down', 'unknown')
TONES = ('', 'ok', 'warn', 'err')
MAX_CHECKS = 50        # per plugin
MAX_METRICS = 6


def _text(value, limit):
    return '' if value is None else ' '.join(str(value).split())[:limit]


def _link(value):
    value = _text(value, 300)
    return value if value.startswith('/') and not value.startswith('//') else ''


def _metric(raw):
    if not isinstance(raw, dict) or not raw.get('label'):
        return None
    value = raw.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        value = _text(value, 40)
    tone = raw.get('tone') if raw.get('tone') in TONES else ''
    return {'label': _text(raw['label'], 40), 'value': value, 'unit': _text(raw.get('unit'), 12), 'tone': tone}


def clean(spec, raw):
    """The checks one plugin returned, cleaned; ids are namespaced by the plugin."""
    if not isinstance(raw, list):
        raise PluginError(f'{spec.name} returned health checks Floorbit can\'t read (not a list)')
    out, seen = [], set()
    for item in raw[:MAX_CHECKS]:
        if not isinstance(item, dict) or not item.get('id') or not item.get('name'):
            continue
        check_id = f"{spec.id}:{_text(item['id'], 40)}"
        if check_id in seen:
            continue
        seen.add(check_id)
        status = item.get('status') if item.get('status') in STATES else 'unknown'
        kind = item.get('kind') if item.get('kind') in KINDS else 'other'
        metrics = [m for m in (_metric(x) for x in (item.get('metrics') or [])[:50]) if m][:MAX_METRICS]
        out.append({'id': check_id, 'name': _text(item['name'], 60), 'kind': kind, 'status': status,
                    'summary': _text(item.get('summary'), 120), 'metrics': metrics,
                    'link': _link(item.get('link')), 'plugin': spec.id, 'plugin_name': spec.name})
    return out


class _FeedSpec:
    """What ``clean`` needs of a plugin, for checks that came from the local agent."""

    def __init__(self, plugin_id, name):
        self.id, self.name = plugin_id, name


class HealthWall:
    def __init__(self, registry):
        self.registry = registry
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.reset()

    def reset(self):
        """Forget everything seen so far; the next poll is a baseline again."""
        self.checks = {}          # id -> the last cleaned check, with 'since'
        self.confirmed = {}       # id -> the status that counts (what alerts are about)
        self._pending = {}        # id -> (candidate status, times seen)
        self.baseline_done = False
        self.last_poll = None
        self.errors = {}          # plugin id -> message of its last failed call

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='health-wall', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    @staticmethod
    def interval():
        return config.get_int('HEALTH_INTERVAL', 30, minimum=10)

    def _run(self):
        while not self._stop.is_set():
            if features.on('health') and (self.registry.feeders('health') or self._agent_active()
                                          or game_servers.listing()):
                try:
                    self.poll_once()
                except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                    print(f'[health] poll failed: {exc}')
            self._stop.wait(self.interval())

    @staticmethod
    def _agent_active():
        from . import agent_link
        return agent_link.active()

    # ── polling ───────────────────────────────────────────────────────────────
    def _from_agent(self):
        """A hosted Floorbit: the health plugins on the local agent, checking from the event
        network. Returns (checks, errors, plugin ids the agent answered for)."""
        from . import agent_link
        found, errors, answered = [], {}, set()
        try:
            feeds = agent_link.feeds('health_feeds')
        except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
            errors['agent'] = str(exc)
            found.append({'id': 'agent:*', 'name': 'Local agent', 'kind': 'other', 'status': 'unknown',
                          'summary': 'The local agent did not answer, so its checks are unknown.', 'metrics': [],
                          'link': '/settings/agents', 'plugin': 'agent', 'plugin_name': 'Local agent'})
            return found, errors, answered
        for feed in feeds:
            spec = _FeedSpec(feed['plugin'], f"{feed['name']} (local agent)")
            if 'error' in feed:
                errors[spec.id] = feed['error']
                found.append({'id': f'{spec.id}:*', 'name': spec.name, 'kind': 'other', 'status': 'unknown',
                              'summary': 'The check failed on the local agent.', 'metrics': [], 'link': '',
                              'plugin': spec.id, 'plugin_name': spec.name})
                continue
            try:
                found += clean(spec, feed['items'])
                answered.add(feed.get('base', feed['plugin']))
            except PluginError as exc:
                errors[spec.id] = str(exc)
        return found, errors, answered

    def _collect(self):
        from . import agent_link
        found, errors, answered = self._from_agent() if agent_link.active() else ([], {}, set())
        found += game_servers.health_checks()     # asked by their own poller (floorbit/game_servers.py)
        for spec in self.registry.feeders('health'):
            if spec.id in answered:    # the agent checks it from the event network; this side can't
                continue
            try:
                found += clean(spec, self.registry.call(spec, 'health_checks'))
            except PluginError as exc:
                errors[spec.id] = str(exc)
                # A plugin that can't answer is one grey tile, not silently missing services.
                found.append({'id': f'{spec.id}:*', 'name': spec.name, 'kind': 'other', 'status': 'unknown',
                              'summary': 'The check failed; details are in the plugin log.', 'metrics': [],
                              'link': '', 'plugin': spec.id, 'plugin_name': spec.name})
        return found, errors

    def poll_once(self):
        """Ask every health plugin once. Returns the confirmed changes."""
        found, errors = self._collect()
        now = time.time()
        need = config.get_int('HEALTH_CONFIRM', 2, minimum=1)
        changes = []
        with self._lock:
            previous = self.checks
            self.checks = {}
            for check in found:
                old = previous.get(check['id'])
                since = old['since'] if old and old['status'] == check['status'] else now
                self.checks[check['id']] = {**check, 'since': since}
                was = self.confirmed.get(check['id'])
                if not self.baseline_done or was is None:
                    self.confirmed[check['id']] = check['status']
                    continue
                if check['status'] == was:
                    self._pending.pop(check['id'], None)
                    continue
                candidate, seen = self._pending.get(check['id'], (None, 0))
                seen = seen + 1 if candidate == check['status'] else 1
                if seen < need:
                    self._pending[check['id']] = (check['status'], seen)
                    continue
                self._pending.pop(check['id'], None)
                self.confirmed[check['id']] = check['status']
                changes.append({'id': check['id'], 'name': check['name'], 'kind': check['kind'],
                                'status': check['status'], 'previous': was, 'summary': check['summary']})
            # Services a plugin stopped reporting (or a plugin turned off) leave the wall quietly.
            for gone in set(self.confirmed) - set(self.checks):
                self.confirmed.pop(gone, None)
                self._pending.pop(gone, None)
            self.baseline_done = True
            self.last_poll = now
            self.errors = errors
        if changes:
            events.publish('health.changed', {'changes': changes})
        return changes

    def fresh(self):
        """The wall, polled now when the background thread hasn't (tests, or the first request)."""
        if self.last_poll is None or time.time() - self.last_poll > 2 * self.interval():
            self.poll_once()
        return self.snapshot()

    def snapshot(self):
        with self._lock:
            checks = sorted(self.checks.values(), key=lambda c: (KINDS.index(c['kind']), c['name'].lower()))
            counts = {s: sum(c['status'] == s for c in checks) for s in STATES}
            return {'checks': checks, 'counts': counts, 'last_poll': self.last_poll,
                    'interval': self.interval(),
                    'plugins': len(self.registry.feeders('health')) + (1 if self._agent_active() else 0)
                    + (1 if game_servers.listing() else 0)}


def init_health(app, registry, start_background=True):
    wall = HealthWall(registry)
    app.extensions['floorbit_health'] = wall
    events.subscribe('health.changed', lambda ev: [
        registry.emit('health.status', change) for change in (ev.get('data') or {}).get('changes', [])])
    started = threading.Event()

    @app.before_request
    def start_health_once():
        # Started on the first request, like the status monitor: the debug reloader imports twice.
        if start_background and not started.is_set():
            started.set()
            wall.start()

    return wall
