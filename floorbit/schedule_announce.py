"""Tell attendees on Discord what is about to start (issue #430). See docs/schedule.md.

A background thread looks at the public programme every half minute. An item that starts within
``SCHEDULE_ANNOUNCE_MINUTES`` (10) is announced once, through the ``schedule.starting`` event, which
the Discord notifier posts to ``DISCORD_SCHEDULE_WEBHOOK_URL``. Only while the public schedule page
is on: the announcement says nothing the page doesn't.

What was announced is kept in memory: after a restart an item inside the window may be announced
a second time, which beats missing it.
"""
import threading
import time

from integrations import config, events

from . import schedule

TICK = 30


def lead_seconds():
    return config.get_int('SCHEDULE_ANNOUNCE_MINUTES', 10, minimum=0) * 60


def starting_soon(items, now, lead):
    """The items that start after now and at most ``lead`` seconds from now, earliest first."""
    return sorted((i for i in items if now < i['start'] <= now + lead), key=lambda i: i['start'])


class Announcer:
    def __init__(self, app):
        self.app = app
        self.seen = set()       # "<id>:<start>": a moved item is announced again at its new time
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='schedule-announce', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                print(f'[schedule] announcing failed: {exc}')
            self._stop.wait(TICK)

    def tick(self, now=None):
        """Announce what is due. Returns the items announced."""
        now = time.time() if now is None else now
        lead = lead_seconds()
        if not lead or not config.get('DISCORD_SCHEDULE_WEBHOOK_URL'):
            return []
        with self.app.app_context():
            if not self.app.extensions['floorbit_settings'].get('public.schedule'):
                return []
            due = []
            for item in starting_soon(schedule.public(now=now)['items'], now, lead):
                key = f"{item['id']}:{item['start']}"
                if key not in self.seen:
                    self.seen.add(key)
                    due.append(item)
            if due:
                base = (self.app.extensions['auth'].public_url() or '').rstrip('/')
                events.publish('schedule.starting', {'items': due, 'page_url': f'{base}/agenda' if base else None})
        return due


def init_schedule_announce(app, start_background=True):
    announcer = Announcer(app)
    app.extensions['floorbit_schedule_announce'] = announcer
    started = threading.Event()

    @app.before_request
    def start_announcer_once():
        # Started on the first request, like the status monitor: the debug reloader imports twice.
        if start_background and not started.is_set():
            started.set()
            announcer.start()

    return announcer
