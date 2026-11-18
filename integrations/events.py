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
import random
import shlex
import sys
import threading
import time

from . import config

_subscribers = []          # [(type or '*', callback)]
_clients = set()           # one queue per open SSE connection
_lock = threading.Lock()
_ids = itertools.count(1)

CLIENT_QUEUE_SIZE = 200
KEEPALIVE_SECONDS = 15
# Each open stream holds one of gunicorn's threads for as long as the tab is open. Without a cap,
# 64 tabs (or one script opening 64 streams, the endpoint needs no sign-in) took every thread, and
# the whole app, the agent's posts included, stopped answering. These are kept for everything else.
RESERVED_THREADS = 16
DEFAULT_STREAMS = 48       # when the thread count isn't known (the dev server)
BUSY_RETRY = (20, 40)      # seconds a turned-away browser waits before it tries again
_anonymous = [0]


def _server_threads():
    """gunicorn's --threads, from its command line or GUNICORN_CMD_ARGS; None when unknown."""
    args = list(sys.argv[1:])
    with contextlib.suppress(ValueError):
        args += shlex.split(os.environ.get('GUNICORN_CMD_ARGS', ''))
    found = None
    for i, arg in enumerate(args):
        value = None
        if arg == '--threads' and i + 1 < len(args):
            value = args[i + 1]
        elif arg.startswith('--threads='):
            value = arg.split('=', 1)[1]
        if value is not None:
            with contextlib.suppress(ValueError):
                found = int(value)   # the last one wins, as in gunicorn
    return found


def max_streams():
    """Open streams allowed at once (LIVE_MAX_STREAMS, else the threads less RESERVED_THREADS)."""
    threads = _server_threads()
    default = max(4, threads - RESERVED_THREADS) if threads else DEFAULT_STREAMS
    return config.get_int('LIVE_MAX_STREAMS', default, minimum=1)


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
        # a stuck browser loses events; it resyncs on reconnect
        with contextlib.suppress(queue.Full):
            q.put_nowait(event)


def client_count():
    with _lock:
        return len(_clients)


def _format(event):
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


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


def _busy():
    # A 200 that ends at once with a long retry: a browser reconnects by itself later, while an
    # error status would make it give up on live updates until the page is reloaded.
    yield f'retry: {random.randint(*BUSY_RETRY) * 1000}\n\n'
    yield ': busy, too many open live-update streams\n\n'


def stream(hello=None, private=True, anonymous=False):
    """Generator for a Flask streaming response. ``private=False`` drops PERSONAL fields.
    ``anonymous`` streams (no sign-in) get at most half the slots, so the crew still gets theirs."""
    q = queue.Queue(maxsize=CLIENT_QUEUE_SIZE)
    # The slot is taken here, once the response is being sent, so a stream that never starts
    # can't keep one.
    cap = max_streams()
    with _lock:
        full = len(_clients) >= cap or (anonymous and _anonymous[0] >= max(1, cap // 2))
        if not full:
            _clients.add(q)
            _anonymous[0] += anonymous
    if full:
        yield from _busy()
        return
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
            yield _format(event if private else {**event, 'data': scrub(event.get('data'))})
    finally:
        with _lock:
            _clients.discard(q)
            _anonymous[0] -= anonymous
