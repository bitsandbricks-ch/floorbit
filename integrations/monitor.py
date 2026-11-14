"""Background switch status monitor.

Every ``STATUS_MONITOR_INTERVAL`` seconds it asks the monitoring plugin (LibreNMS) for all
devices in one request, matches them to the switches placed on the floor plan, and
publishes events when a switch changes status:

* ``switch.status``  one per confirmed change: {id, name, status, previous}
* ``monitor.poll``   once per poll: {changes: [...], counts: {...}}

The first poll only records a baseline, so restarting the app does not fire
a wave of alerts. A change has to be seen ``STATUS_MONITOR_CONFIRM`` polls in
a row before it counts, so a single missed SNMP poll does not page anyone.
"""
import threading
import time

from . import config, events


class StatusMonitor:
    def __init__(self, list_switches):
        self._list_switches = list_switches
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.statuses = {}        # id -> {'id','name','status','since'}
        self._pending = {}        # id -> (candidate status, times seen)
        self.baseline_done = False
        self.last_poll = None
        self.last_error = None
        self.tracked = 0

    # ── lifecycle ─────────────────────────────────────────────────────────────────────────
    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='status-monitor', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            interval = config.get_int('STATUS_MONITOR_INTERVAL', 60, minimum=10)
            if self.enabled():
                try:
                    self.poll_once()
                except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                    self.last_error = str(exc)
                    print(f"[integrations] status monitor poll failed: {exc}")
            self._stop.wait(interval)

    # ── config ────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def source():
        from floorbit import sources
        return sources.monitoring()

    def enabled(self):
        return self.source().enabled() and config.get_bool('STATUS_MONITOR_ENABLED', True)

    # ── polling ───────────────────────────────────────────────────────────────────────────
    def fetch_devices(self):
        return self.source().devices()

    @staticmethod
    def match(name, devices):
        """Find the LibreNMS device for a floor-plan switch name.

        Same preference order as the rest of the app: exact display name,
        exact hostname/sysName, then short-name (before the first dot).
        """
        n = (name or '').strip().lower()
        if not n:
            return None
        short = n.split('.')[0]
        fields = ('display', 'hostname', 'sysName')
        for d in devices:
            if (d.get('display') or '').lower() == n:
                return d
        for d in devices:
            if any((d.get(f) or '').lower() == n for f in fields[1:]):
                return d
        for d in devices:
            if any((d.get(f) or '').lower().split('.')[0] == short for f in fields):
                return d
        return None

    @staticmethod
    def device_status(device):
        if device is None:
            return 'unknown'
        if device.get('disabled') in (1, '1', True) or device.get('ignore') in (1, '1', True):
            return 'unknown'
        return 'online' if device.get('status') in (1, '1', True) else 'offline'

    def poll_once(self):
        from floorbit import sources
        source = self.source()
        try:
            devices = self.fetch_devices()
        except Exception as exc:
            # One message per outage, and no "switch down" flood: nothing is compared while it's down.
            if sources.mark_failed(source.name, exc):
                events.publish('monitoring.offline', {'source': source.label, 'error': str(exc)[:300],
                                                      'since': sources.health()['offline_since']})
            raise
        down_for = sources.mark_ok(source.name)
        if down_for is not None:
            # Switches may have changed while the source was down: start over from a fresh baseline
            # instead of announcing every difference at once.
            self.baseline_done = False
            events.publish('monitoring.online', {'source': source.label, 'down_for': down_for})
        switches = self._list_switches()
        confirm = config.get_int('STATUS_MONITOR_CONFIRM', 2, minimum=1)
        now = time.time()
        changes = []
        seen = set()

        for sw in switches:
            sid = sw['id']
            seen.add(sid)
            device = self.match(sw['name'], devices)
            status = self.device_status(device)
            current = self.statuses.get(sid)

            if current is None or not self.baseline_done:
                self.statuses[sid] = {'id': sid, 'name': sw['name'], 'status': status, 'since': now}
                self._pending.pop(sid, None)
                continue

            current['name'] = sw['name']
            if status == current['status']:
                self._pending.pop(sid, None)
                continue

            candidate, count = self._pending.get(sid, (None, 0))
            count = count + 1 if candidate == status else 1
            if count < confirm:
                self._pending[sid] = (status, count)
                continue

            self._pending.pop(sid, None)
            change = {
                'id': sid,
                'name': sw['name'],
                'status': status,
                'previous': current['status'],
                'since': now,
                'down_for': now - current['since'] if current['status'] == 'offline' else None,
                'reason': (device or {}).get('status_reason') or None,
                'source': sw.get('source'),
            }
            current['status'] = status
            current['since'] = now
            changes.append(change)

        # Forget switches that were removed from the floor plan
        for sid in list(self.statuses):
            if sid not in seen:
                self.statuses.pop(sid, None)
                self._pending.pop(sid, None)

        self.baseline_done = True
        self.last_poll = now
        self.last_error = None
        self.tracked = len(seen)

        for change in changes:
            events.publish('switch.status', change)
        events.publish('monitor.poll', {'changes': changes, 'counts': self.counts()})
        return changes

    # ── read side ────────────────────────────────────────────────────────────────────────
    def counts(self):
        out = {'online': 0, 'offline': 0, 'unknown': 0}
        for s in self.statuses.values():
            out[s['status']] = out.get(s['status'], 0) + 1
        return out

    def snapshot(self):
        return {sid: s['status'] for sid, s in self.statuses.items()}

    def info(self):
        return {
            'enabled': self.enabled(),
            'running': bool(self._thread and self._thread.is_alive()),
            'interval': config.get_int('STATUS_MONITOR_INTERVAL', 60, minimum=10),
            'confirm_polls': config.get_int('STATUS_MONITOR_CONFIRM', 2, minimum=1),
            'last_poll': self.last_poll,
            'last_error': self.last_error,
            'tracked': self.tracked,
            'counts': self.counts(),
        }
