"""The event bus and the Server-Sent Events stream.

Anything in the app can ``publish(type, data)``. Python subscribers (Discord
alerts, for example) get a callback, and every open browser gets the event
over ``GET /api/events``.

With several pods (``FLOORBIT_CLUSTER=redis``, floorbit/cluster.py) an event
also reaches the browsers on the other pods. Subscribers marked
``leader_only`` (the ones that post, send or write: Discord, webhooks, the
timeline) skip events from background loops unless this pod is the leader,
since every pod runs those loops and the alert should go out once.
"""
import contextlib
import itertools
import json
import os
import queue
import signal
import threading
import time

from . import config

_subscribers = []          # [(type or '*', callback)]
_clients = set()           # one queue per open SSE connection
_lock = threading.Lock()
_ids = itertools.count(1)

CLIENT_QUEUE_SIZE = 200
KEEPALIVE_SECONDS = 15
_CLOSE = object()          # put in a client queue: end that stream
_closing = threading.Event()
# The server's threads per process, which gunicorn.conf.py writes down after each fork.
THREADS_ENV = 'FLOORBIT_SERVER_THREADS'


def subscribe(event_type, callback, leader_only=False):
    """Call ``callback(event)`` for every event of ``event_type`` ('*' for all)."""
    with _lock:
        _subscribers.append((event_type, callback, leader_only))


def subscribe_once(event_type, callback, leader_only=False):
    """Like ``subscribe``, but only if this callback isn't subscribed to ``event_type`` yet."""
    with _lock:
        if not any(t == event_type and cb == callback for t, cb, _ in _subscribers):
            _subscribers.append((event_type, callback, leader_only))


def _from_background():
    from flask import has_request_context
    return not has_request_context()


def publish(event_type, data=None, origin=None):
    event = {
        'id': next(_ids),
        'type': event_type,
        'ts': time.time(),
        'origin': origin,
        'data': data or {},
    }
    from floorbit import cluster
    follower = not cluster.leading() and _from_background()
    with _lock:
        subs = [cb for t, cb, leader_only in _subscribers if t in ('*', event_type) and not (leader_only and follower)]
    for cb in subs:
        try:
            cb(event)
        except Exception as exc:  # noqa: BLE001  # one bad subscriber must not stop the others
            print(f"[integrations] subscriber for {event_type} failed: {exc}")
    deliver_local(event)
    if cluster.current is not None:
        cluster.current.publish(event)
    return event


def deliver_local(event):
    """Hand an event to the browsers connected to this pod."""
    if not config.get_bool('LIVE_UPDATES_ENABLED', True):
        return
    with _lock:
        clients = list(_clients)
    for q in clients:
        try:
            q.put_nowait(event)
        except queue.Full:
            q.missed = True     # a stuck browser: told to fetch everything again once it reads on


def resync_all():
    """Tell every browser here to fetch everything again: events may have been missed (another
    pod's changes while Redis was away)."""
    deliver_local(_resync_event())


def _resync_event():
    return {'id': 0, 'type': 'resync', 'ts': time.time(), 'origin': None, 'data': {}}


def close_all():
    """End every open stream. The browsers reconnect after ``retry`` (to the next pod, in an update).

    Without it an open tab kept its request running, so a stopping worker waited out gunicorn's whole
    graceful timeout (30 s) on every restart and was then killed.
    """
    _closing.set()
    with _lock:
        clients = list(_clients)
    for q in clients:
        # Wakes a stream waiting on an empty queue; one with a full queue sees _closing next round.
        with contextlib.suppress(queue.Full):
            q.put_nowait(_CLOSE)


def close_streams_on_sigterm():
    """Run ``close_all`` before the server's own SIGTERM handler (gunicorn's worker sets one).

    Only from the main thread, and only on top of a handler that is a function: with no server
    handler (tests, ``flask run``) SIGTERM keeps its default.
    """
    if threading.current_thread() is not threading.main_thread():
        return False
    previous = signal.getsignal(signal.SIGTERM)
    if not callable(previous) or getattr(previous, 'closes_streams', False):
        return False

    def on_sigterm(signum, frame):
        close_all()
        previous(signum, frame)

    on_sigterm.closes_streams = True
    signal.signal(signal.SIGTERM, on_sigterm)
    return True


def client_count():
    with _lock:
        return len(_clients)


def stream_limit():
    """How many live streams this process takes, or None when the server doesn't say (``flask run``,
    tests). Each open stream holds one of the server's threads until the tab closes: 64 open tabs
    used to take all 64 and no page loaded any more, so a quarter (at least 8) stays for requests."""
    try:
        threads = int(os.environ.get(THREADS_ENV) or 0)
    except ValueError:
        return None
    if threads <= 8:
        return None
    return threads - max(8, threads // 4)


def admit(crew):
    """Whether one more stream fits. Readers who aren't signed in (attendees on the status page)
    get at most half, so a hall full of phones can't keep the crew's pages from updating."""
    limit = stream_limit()
    if limit is None:
        return True
    with _lock:
        total = len(_clients)
        public = sum(1 for q in _clients if not getattr(q, 'crew', True))
    return total < limit and (crew or public < limit // 2)


def _format(event):
    try:
        data = json.dumps(event, default=str, allow_nan=False)
    except ValueError:
        # A bare NaN (a device's odd reading) made the page's JSON.parse throw on this event.
        from floorbit.json_body import finite
        data = json.dumps(finite(event), default=str)
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {data}\n\n"


# Who did what: nicks and account names, and the IP and MAC a check-in came from. Only readers who may
# see people (seats.view) get them; the stream is open to the kiosk and, by default, to anyone.
PERSONAL = frozenset(('username', 'nick', 'nicks', 'ip', 'mac', 'assignee', 'user', 'by'))


def scrub(value):
    """``value`` without PERSONAL keys, at any depth."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k not in PERSONAL}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def stream(hello=None, private=True, crew=True):
    """Generator for a Flask streaming response. ``private=False`` drops PERSONAL fields; ``crew``
    says whether the reader is signed in (``admit``)."""
    q = queue.Queue(maxsize=CLIENT_QUEUE_SIZE)
    q.crew = crew
    with _lock:
        _clients.add(q)
    try:
        yield 'retry: 5000\n\n'
        yield _format({'id': 0, 'type': 'hello', 'ts': time.time(), 'origin': None,
                       'data': hello or {}})
        while not _closing.is_set():
            try:
                event = q.get(timeout=KEEPALIVE_SECONDS)
            except queue.Empty:
                yield ': keepalive\n\n'
                continue
            if event is _CLOSE:
                return
            if getattr(q, 'missed', False):
                q.missed = False
                yield _format(_resync_event())
            yield _format(event if private else {**event, 'data': scrub(event.get('data'))})
    finally:
        with _lock:
            _clients.discard(q)
