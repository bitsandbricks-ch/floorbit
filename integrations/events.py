"""In-process event bus and the Server-Sent Events stream.

Anything in the app can ``publish(type, data)``. Python subscribers (Discord
alerts, for example) get a callback, and every open browser gets the event
over ``GET /api/events``.

The bus lives in one process. That matches how the app runs today
(``python app.py``, threaded). Running several worker processes would need a
shared channel such as Redis pub/sub; ``publish`` is the single place to add it.
"""
import contextlib
import itertools
import json
import queue
import threading
import time

from . import config

_subscribers = []          # [(type or '*', callback)]
_clients = set()           # one queue per open SSE connection
_lock = threading.Lock()
_ids = itertools.count(1)

CLIENT_QUEUE_SIZE = 200
KEEPALIVE_SECONDS = 15


def subscribe(event_type, callback):
    """Call ``callback(event)`` for every event of ``event_type`` ('*' for all)."""
    with _lock:
        _subscribers.append((event_type, callback))


def publish(event_type, data=None, origin=None):
    event = {
        'id': next(_ids),
        'type': event_type,
        'ts': time.time(),
        'origin': origin,
        'data': data or {},
    }
    with _lock:
        subs = [cb for t, cb in _subscribers if t in ('*', event_type)]
        clients = list(_clients)
    for cb in subs:
        try:
            cb(event)
        except Exception as exc:  # noqa: BLE001  # one bad subscriber must not stop the others
            print(f"[integrations] subscriber for {event_type} failed: {exc}")
    if config.get_bool('LIVE_UPDATES_ENABLED', True):
        for q in clients:
            # a stuck browser loses events; it resyncs on reconnect
            with contextlib.suppress(queue.Full):
                q.put_nowait(event)
    return event


def client_count():
    with _lock:
        return len(_clients)


def _format(event):
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


def stream(hello=None):
    """Generator for a Flask streaming response."""
    q = queue.Queue(maxsize=CLIENT_QUEUE_SIZE)
    with _lock:
        _clients.add(q)
    try:
        yield 'retry: 5000\n\n'
        yield _format({'id': 0, 'type': 'hello', 'ts': time.time(), 'origin': None,
                       'data': hello or {}})
        while True:
            try:
                event = q.get(timeout=KEEPALIVE_SECONDS)
            except queue.Empty:
                yield ': keepalive\n\n'
                continue
            yield _format(event)
    finally:
        with _lock:
            _clients.discard(q)
