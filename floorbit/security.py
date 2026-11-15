"""Security detection (issue #29): rogue DHCP servers, ARP spoofing, MAC flapping, loops and
broadcast storms, each pointing at a switch port and, where Floorbit can tell, a seat. See
docs/security.md.

Detection lives in plugins with ``uses: [security]``; ``security_findings()`` returns what the
plugin sees right now::

    [{"id": "arp-192.0.2.10", "kind": "arp-spoof", "severity": "high",
      "title": "192.0.2.10 answered by two MACs", "detail": "...",
      "switch": "sw-b-01", "port": "Gi1/0/4", "mac": "02:00:00:00:00:1b", "ip": "192.0.2.10",
      "evidence": ["02:00:00:00:00:1b on Gi1/0/4", "02:00:00:00:00:2c on Gi1/0/9"]}]

A background thread asks every security plugin each ``SECURITY_INTERVAL`` seconds. A finding a
plugin stops reporting is cleared and kept in the recent list for an hour. A new finding
publishes ``security.finding`` (Discord, plugin hooks, the floor plan), from the second round
on, so a restart doesn't page anyone again. Findings hold MACs and IPs: personal data, so the
API needs ``seats.view`` and Discord messages carry only the switch, port and seat.
"""
import threading
import time

from integrations import config, events

from . import features
from .plugins import PluginError

KINDS = ('rogue-dhcp', 'arp-spoof', 'mac-flap', 'loop', 'storm', 'other')
SEVERITIES = ('high', 'medium', 'low')
MAX_FINDINGS = 200        # per plugin
KEEP_CLEARED = 3600       # seconds a cleared finding stays in the recent list
MAX_CLEARED = 200

_watch = None             # the app's SecurityWatch, for floorbit.ports


def _text(value, limit):
    return '' if value is None else ' '.join(str(value).split())[:limit]


def _mac(value):
    raw = ''.join(c for c in str(value or '').lower() if c in '0123456789abcdef')
    return ':'.join(raw[i:i + 2] for i in range(0, 12, 2)) if len(raw) == 12 else ''


def clean(spec, raw):
    if not isinstance(raw, list):
        raise PluginError(f"{spec.name} returned security findings Floorbit can't read (not a list)")
    out, seen = [], set()
    for item in raw[:MAX_FINDINGS]:
        if not isinstance(item, dict) or not item.get('id') or not item.get('title'):
            continue
        finding_id = f"{spec.id}:{_text(item['id'], 60)}"
        if finding_id in seen:
            continue
        seen.add(finding_id)
        out.append({
            'id': finding_id, 'plugin': spec.id, 'plugin_name': spec.name,
            'kind': item.get('kind') if item.get('kind') in KINDS else 'other',
            'severity': item.get('severity') if item.get('severity') in SEVERITIES else 'medium',
            'title': _text(item['title'], 120), 'detail': _text(item.get('detail'), 500),
            'switch': _text(item.get('switch'), 80), 'port': _text(item.get('port'), 48),
            'seat': _text(item.get('seat'), 20).upper(), 'mac': _mac(item.get('mac')),
            'ip': _text(item.get('ip'), 45),
            'evidence': [_text(e, 160) for e in (item.get('evidence') or [])[:10] if e],
        })
    return out


def _seat_index():
    """MAC and IP -> seat, from the seat mapping."""
    try:
        from integrations import seat_sources
        mapping = seat_sources.load() or {}
    except Exception:  # noqa: BLE001  # findings still show without seats
        return {}
    index = {}
    for seat, entry in mapping.items():
        if not isinstance(entry, dict):
            continue
        mac = _mac(entry.get('mac') or entry.get('mac_address'))
        if mac:
            index[mac] = seat
        if entry.get('ip_address'):
            index[str(entry['ip_address'])] = seat
    return index


class SecurityWatch:
    def __init__(self, registry):
        self.registry = registry
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.reset()

    def reset(self):
        self.findings = {}        # id -> active finding
        self.cleared = []         # recently cleared, newest first
        self.baseline_done = False
        self.last_poll = None

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='security-watch', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    @staticmethod
    def interval():
        return config.get_int('SECURITY_INTERVAL', 60, minimum=15)

    def _run(self):
        while not self._stop.is_set():
            if features.on('security') and self.registry.feeders('security'):
                try:
                    self.poll_once()
                except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                    print(f'[security] poll failed: {exc}')
            self._stop.wait(self.interval())

    # ── polling ───────────────────────────────────────────────────────────────
    def poll_once(self):
        """Ask every security plugin once. Returns the new findings."""
        found, failed = [], set()
        for spec in self.registry.feeders('security'):
            try:
                found += clean(spec, self.registry.call(spec, 'security_findings'))
            except PluginError:
                failed.add(spec.id)   # its findings stay as they were: a failed check clears nothing
        index = _seat_index()
        now = time.time()
        new = []
        with self._lock:
            current = {}
            for f in found:
                # The MAC is the device at fault; its IP may be someone else's (ARP spoofing), so the IP
                # only counts when the plugin gave no MAC. A wrong seat would send a tech to the victim.
                f['seat'] = f['seat'] or (index.get(f['mac'], '') if f['mac'] else index.get(f['ip'], ''))
                old = self.findings.get(f['id'])
                current[f['id']] = {**f, 'first_seen': old['first_seen'] if old else now, 'last_seen': now,
                                    'ack': old.get('ack') if old else None}
                if not old and self.baseline_done:
                    new.append(current[f['id']])
            for fid, old in self.findings.items():
                if fid in current:
                    continue
                if old['plugin'] in failed:
                    current[fid] = old
                else:
                    self.cleared.insert(0, {**old, 'cleared_at': now})
            self.cleared = [c for c in self.cleared if now - c['cleared_at'] < KEEP_CLEARED][:MAX_CLEARED]
            self.findings = current
            self.baseline_done = True
            self.last_poll = now
        for f in new:
            # Every open browser gets this event too: no title, MAC or IP, which can name a person.
            events.publish('security.finding', {k: f[k] for k in (
                'id', 'kind', 'severity', 'switch', 'port', 'seat')})
        return new

    def fresh(self):
        if self.last_poll is None or time.time() - self.last_poll > 2 * self.interval():
            self.poll_once()
        return self.snapshot()

    def snapshot(self):
        order = {s: i for i, s in enumerate(SEVERITIES)}
        with self._lock:
            active = sorted(self.findings.values(),
                            key=lambda f: (f['ack'] is not None, order[f['severity']], -f['first_seen']))
            return {'findings': active, 'cleared': list(self.cleared), 'last_poll': self.last_poll,
                    'interval': self.interval(), 'plugins': len(self.registry.feeders('security'))}

    def get(self, finding_id):
        with self._lock:
            f = self.findings.get(finding_id)
            return dict(f) if f else None

    def acknowledge(self, finding_id, user, on=True):
        with self._lock:
            f = self.findings.get(finding_id)
            if not f:
                return None
            f['ack'] = {'by': user, 'at': time.time()} if on else None
            return dict(f)


def get(finding_id):
    return _watch.get(finding_id) if _watch else None


def init_security(app, registry, start_background=True):
    global _watch
    watch = _watch = SecurityWatch(registry)
    app.extensions['floorbit_security'] = watch
    events.subscribe('security.finding', lambda ev: registry.emit('security.finding', ev.get('data') or {}))
    started = threading.Event()

    @app.before_request
    def start_security_once():
        if start_background and not started.is_set():
            started.set()
            watch.start()

    return watch
