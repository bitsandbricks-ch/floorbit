"""Background switch status monitor.

Every ``STATUS_MONITOR_INTERVAL`` seconds it asks the monitoring plugin (LibreNMS) for all
devices in one request, matches them to the switches placed on the floor plan, and
publishes events when a switch changes status:

* ``switch.status``  one per confirmed change: {id, name, status, previous}
* ``monitor.poll``   once per poll: {changes: [...], counts: {...}}

The first poll only records a baseline, so restarting the app does not fire
a wave of alerts. A change has to be seen ``STATUS_MONITOR_CONFIRM`` polls in
a row before it counts, so a single missed SNMP poll does not page anyone.

With several pods (or gunicorn workers) only the leader polls and shares what it saw through
floorbit/shared_state.py; the other pods read that (issue #1417).
"""
import threading
import time
from typing import ClassVar

from . import config, events

SHARED = 'monitor'
FOLLOW_EVERY = 5      # how often a pod that doesn't lead checks whether it leads now


class StatusMonitor:
    # The device list of the last poll that answered, and when it was asked: other pages (firewalls)
    # read it instead of asking a monitoring source that may be hanging. None until a poll ran.
    latest: ClassVar[dict] = {'polled': None, 'at': None, 'devices': None}

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
        from floorbit import sources
        self._stop.set()
        sources.wake_status_monitor()   # out of its wait

    def _run(self):
        from floorbit import cluster
        led = False
        while not self._stop.is_set():
            interval = config.get_int('STATUS_MONITOR_INTERVAL', 60, minimum=10)
            leading = cluster.leading()
            if not leading:
                led = False
                self._stop.wait(FOLLOW_EVERY)
                continue
            try:
                if not led:
                    led = True
                    self.take_over()
                if self.enabled():
                    self.poll_once()
            except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                self.last_error = str(exc)
                self.share()
                print(f"[integrations] status monitor poll failed: {exc}")
            from floorbit import sources
            if sources.status_wake.wait(interval):
                sources.status_wake.clear()
                self._stop.wait(1)      # the agent's first calls go ahead of the device list

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
            StatusMonitor.latest.update(polled=time.time(), at=time.time(), devices=devices)
        except Exception as exc:
            StatusMonitor.latest['polled'] = time.time()
            # One message per outage, and no "switch down" flood: nothing is compared while it's down.
            if sources.mark_failed(source.name, exc, source.label):
                data = {'source': source.label, 'error': str(exc)[:300], 'since': sources.health()['offline_since']}
                if source.name == 'agent':
                    # A hosted Floorbit: the agent, not LibreNMS, is what's gone. Say when it was last heard.
                    from floorbit import agent_link
                    data.update(agent=True, last_seen=agent_link.tunnel.last_seen)
                events.publish('monitoring.offline', data)
            raise
        down_for = sources.mark_ok(source.name, source.label)
        try:
            from floorbit import librenms_alerts
            librenms_alerts.maybe_reconcile(source)   # an alert whose recovery got lost (#951)
        except Exception as exc:  # noqa: BLE001  # never let this stop the status poll
            print(f'[monitor] checking LibreNMS alerts failed: {exc}')
        if down_for is not None:
            # Switches may have changed while the source was down: start over from a fresh baseline
            # instead of announcing every difference at once.
            self.baseline_done = False
            events.publish('monitoring.online', {'source': source.label, 'down_for': down_for,
                                                 **({'agent': True} if source.name == 'agent' else {})})
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
            current['previous'] = change['previous']   # tells "came back" apart from "was always up" (issue #390)
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

        self.share()
        for change in changes:
            events.publish('switch.status', change)
        events.publish('monitor.poll', {'changes': changes, 'counts': self.counts()})
        return changes

    # ── several pods ─────────────────────────────────────────────────────────────────────
    def share(self):
        """What the other pods' pages read (only the leader polls)."""
        from floorbit import shared_state, sources
        shared_state.put(SHARED, {'statuses': self.statuses, 'baseline_done': self.baseline_done,
                                  'last_poll': self.last_poll, 'last_error': self.last_error,
                                  'tracked': self.tracked, 'latest': StatusMonitor.latest,
                                  'source': sources.health(), 'at': time.time()})

    def take_over(self):
        """This pod leads now: carry on from what the old leader saw, so a switch that went down
        before the handover is still down and comes back with its real outage time."""
        from floorbit import shared_state
        seen = shared_state.get(SHARED)
        if not isinstance(seen, dict) or not isinstance(seen.get('statuses'), dict):
            return
        self.statuses = {sid: dict(s) for sid, s in seen['statuses'].items() if isinstance(s, dict)}
        self._pending = {}
        self.baseline_done = bool(seen.get('baseline_done')) and bool(self.statuses)
        self.last_poll = seen.get('last_poll')

    def _view(self):
        """The leader's picture on a pod that doesn't lead, else this pod's own."""
        from floorbit import shared_state
        if shared_state.follower():
            seen = shared_state.get(SHARED)
            return seen if isinstance(seen, dict) else {'statuses': {}}
        return {'statuses': self.statuses, 'last_poll': self.last_poll, 'last_error': self.last_error,
                'tracked': self.tracked, 'latest': StatusMonitor.latest}

    @classmethod
    def latest_devices(cls):
        """The device list of the last poll (see ``latest``), the leader's on another pod."""
        from floorbit import shared_state
        if shared_state.follower():
            seen = shared_state.get(SHARED)
            latest = seen.get('latest') if isinstance(seen, dict) else None
            return latest if isinstance(latest, dict) else {'polled': None, 'at': None, 'devices': None}
        return cls.latest

    # ── read side ────────────────────────────────────────────────────────────────────────
    def counts(self, view=None):
        out = {'online': 0, 'offline': 0, 'unknown': 0}
        for s in (view or self._view())['statuses'].values():
            out[s['status']] = out.get(s['status'], 0) + 1
        return out

    def snapshot(self):
        return {sid: s['status'] for sid, s in self._view()['statuses'].items()}

    def status_of(self, sid):
        """One switch's status as last seen, or None."""
        return (self._view()['statuses'].get(sid) or {}).get('status')

    def last_polled(self):
        return self._view().get('last_poll')

    def info(self):
        view = self._view()
        return {
            'enabled': self.enabled(),
            'running': bool(self._thread and self._thread.is_alive()),
            'interval': config.get_int('STATUS_MONITOR_INTERVAL', 60, minimum=10),
            'confirm_polls': config.get_int('STATUS_MONITOR_CONFIRM', 2, minimum=1),
            'last_poll': view.get('last_poll'),
            'last_error': view.get('last_error'),
            'tracked': view.get('tracked') or 0,
            'counts': self.counts(view),
        }
