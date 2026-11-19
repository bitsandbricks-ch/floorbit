"""Inventory syncs on a schedule (docs/inventory.md#syncing-on-its-own).

Every ``INVENTORY_SYNC_MINUTES`` the cluster's leader runs the same sync as **Sync now**, so a
switch added in NetBox shows up without anyone pressing the button. Off (0) by default. The clock
counts from the newest sync in the log, by hand or not, so a sync someone just ran isn't repeated.
"""
import calendar
import threading
import time

from integrations import config

from .store import load_data

MIN_MINUTES = 5          # a NetBox with a few thousand devices takes a while; don't queue syncs
MAX_MINUTES = 24 * 60

# One sync at a time from this process; the button and the schedule can meet.
running = threading.Lock()


def every_minutes():
    """Minutes between scheduled syncs, or 0 when off."""
    minutes = config.get_int('INVENTORY_SYNC_MINUTES', 0, minimum=0)
    if minutes <= 0:
        return 0
    return min(max(minutes, MIN_MINUTES), MAX_MINUTES)


def _at(report):
    try:
        return calendar.timegm(time.strptime(report.get('at') or '', '%Y-%m-%dT%H:%M:%SZ'))
    except (TypeError, ValueError):
        return None


def last_sync_at(data):
    """When the newest sync in the log ran (seconds), or None."""
    times = [t for t in (_at(r) for r in data.get('inventory_log') or [] if isinstance(r, dict)) if t]
    return max(times) if times else None


def due(now, last_at, minutes):
    if minutes <= 0:
        return False
    if last_at is None or last_at > now:     # never synced, or the clock went back
        return True
    return now - last_at >= minutes * 60


def tick(now=None):
    """One look at the schedule. Returns the sync's reports, or None when nothing ran."""
    from . import agent_link
    from .blueprints.inventory import _feeders, run_sync
    now = time.time() if now is None else now
    if not due(now, last_sync_at(load_data()), every_minutes()):
        return None
    if not _feeders() and not agent_link.active():
        return None
    if not running.acquire(blocking=False):
        return None
    try:
        return run_sync()
    finally:
        running.release()


def _loop(app, stop):
    from . import cluster
    while not stop.wait(60):
        try:
            if cluster.leading():   # several pods sync once
                with app.app_context():
                    tick()
        except Exception as exc:  # noqa: BLE001  # the loop must outlive one bad sync
            print(f'[inventory] scheduled sync failed: {exc}')


def init_app(app, start_background=True):
    if not start_background:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(app, stop), name='inventory-sync', daemon=True).start()
    return stop
