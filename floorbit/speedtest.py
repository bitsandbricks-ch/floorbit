"""Speedtest at the seat (issue #99): download, upload and latency between a player's machine and
the Floorbit server, from the seat's help page. See docs/speedtest.md.

It proves "it's not the network" (or that it is) up to the server, inside the hall: no internet
speed test. The browser measures; the server only sends and swallows bytes, then keeps the result
per seat: speeds and latency and when, never the IP, browser or anything personal. A result is put
on the seat's open helpdesk incident, and a report filed soon after a test carries it too.

Every stream holds one of the server's threads, which the live updates need too, so only
``MAX_RUNNING`` run at once and each client IP gets a byte budget.
"""
import os
import threading
import time

from .store import load_data, save_data

KEY = 'speedtests'
CHUNK = 64 * 1024
PAYLOAD = os.urandom(1024 * 1024)   # random: nothing on the way can compress it
MAX_DOWN = 200 * 1024 * 1024        # one download request
MAX_UP = 24 * 1024 * 1024           # one upload request (under MAX_CONTENT_LENGTH)
BUDGET = 2 * 1024 * 1024 * 1024     # bytes per client IP per window: about two tests
WINDOW = 600
MAX_RUNNING = 6
KEEP = 5                            # results per seat
FRESH = 30 * 60                     # a test this recent goes with a new report
LIMITS = {'down_mbps': 100000, 'up_mbps': 100000, 'ping_ms': 10000, 'jitter_ms': 10000}

_lock = threading.Lock()
_running = [0]
_spent = {}
_saved = {}


class SpeedtestError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def take(ip, size):
    """Book ``size`` bytes for one stream. Raises SpeedtestError when busy or over the budget."""
    now = time.time()
    with _lock:
        used = [(t, n) for t, n in _spent.get(ip, []) if now - t < WINDOW]
        if sum(n for _t, n in used) + size > BUDGET:
            _spent[ip] = used
            raise SpeedtestError('Too many tests from here. Wait a few minutes.', 429)
        if _running[0] >= MAX_RUNNING:
            raise SpeedtestError('Other seats are testing right now. Try again in a minute.', 503)
        _running[0] += 1
        _spent[ip] = [*used, (now, size)]
        if len(_spent) > 10000:   # forget idle clients so the dict can't grow without bound
            for key in [k for k, v in _spent.items() if not v or now - v[-1][0] > WINDOW]:
                _spent.pop(key, None)


def allow_result(ip, limit=10):
    """At most ``limit`` results per client IP per window: a result is a write anyone at a seat can do."""
    now = time.time()
    with _lock:
        recent = [t for t in _saved.get(ip, []) if now - t < WINDOW]
        if len(recent) >= limit:
            _saved[ip] = recent
            return False
        _saved[ip] = [*recent, now]
        if len(_saved) > 10000:
            for key in [k for k, v in _saved.items() if not v or now - v[-1] > WINDOW]:
                _saved.pop(key, None)
    return True


def release():
    with _lock:
        _running[0] = max(0, _running[0] - 1)


def reset():
    with _lock:
        _running[0] = 0
        _spent.clear()
        _saved.clear()


def download(size):
    """``size`` random bytes in chunks; frees the stream slot when done or cut off."""
    try:
        left = size
        while left > 0:
            for start in range(0, len(PAYLOAD), CHUNK):
                if left <= 0:
                    break
                piece = PAYLOAD[start:start + min(CHUNK, left)]
                left -= len(piece)
                yield piece
    finally:
        release()


def swallow(stream, limit=MAX_UP):
    """Read an upload and drop it. Returns the bytes read."""
    total = 0
    try:
        while total < limit:
            piece = stream.read(min(CHUNK, limit - total))
            if not piece:
                break
            total += len(piece)
    finally:
        release()
    return total


def clean(body):
    """A result from the browser: numbers in range, rounded. Raises SpeedtestError."""
    out = {}
    for key, top in LIMITS.items():
        value = body.get(key)
        if value in (None, ''):
            out[key] = None
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise SpeedtestError(f'{key} is a number.') from None
        if not 0 <= value <= top:
            raise SpeedtestError(f'{key} is 0 to {top}.')
        out[key] = round(value, 1)
    if out['down_mbps'] is None and out['up_mbps'] is None and out['ping_ms'] is None:
        raise SpeedtestError('The test measured nothing.')
    out['at'] = time.time()
    return out


def save(seat, result):
    """Keep the result for the seat and put it on the seat's open helpdesk incident, if there is one."""
    from . import incidents
    with incidents._lock:
        data = load_data()
        kept = data.setdefault(KEY, {})
        kept[seat] = [result, *(kept.get(seat) or [])][:KEEP]
        for incident in data.get(incidents.KEY) or []:
            if incident.get('seat') == seat and incident.get('source') == 'helpdesk' \
                    and incident.get('status') != 'fixed':
                incident['speedtest'] = result
                incident['updated_at'] = result['at']
        save_data(data)
    return result


def results(seat, data=None):
    data = load_data() if data is None else data
    return list((data.get(KEY) or {}).get(seat) or [])


def latest(seat, data=None, max_age=FRESH):
    found = results(seat, data)
    return found[0] if found and time.time() - found[0]['at'] < max_age else None
