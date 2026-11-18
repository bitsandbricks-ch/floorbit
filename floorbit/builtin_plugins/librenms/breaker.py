"""Every request to LibreNMS goes through ``get``: once LibreNMS doesn't answer, the next calls
fail at once for BREAK_FOR seconds instead of each waiting out its own timeout.

Without it a LibreNMS that hangs made pages that ask about many seats or switches wait minutes
(the heatmap asked 144 seats, ten seconds each). The status monitor keeps asking in the background
and notices when it is back.
"""
import threading
import time

import requests

BREAK_FOR = 30   # seconds
_lock = threading.Lock()
_down = {'until': 0.0, 'base': None, 'why': ''}


def _base(url):
    return '/'.join(str(url).split('/')[:3])   # scheme://host[:port]


def get(url, **kwargs):
    now = time.monotonic()
    base = _base(url)
    with _lock:
        if _down['base'] == base and now < _down['until']:
            raise requests.ConnectionError(f"LibreNMS did not answer a moment ago ({_down['why']})")
    # X-Auth-Token is a header of our own, which requests keeps on a redirect to another host (it
    # drops only Authorization): never follow one, as plugins' HttpClient doesn't either.
    kwargs.setdefault('allow_redirects', False)
    try:
        resp = requests.get(url, **kwargs)
    except (requests.ConnectionError, requests.Timeout) as exc:
        with _lock:
            _down.update(until=time.monotonic() + BREAK_FOR, base=base, why=type(exc).__name__)
        raise
    if resp.status_code in (301, 302, 303, 307, 308):   # "ok" to requests, but no answer: say where
        raise requests.HTTPError(f"LibreNMS redirects to {resp.headers.get('Location', '')}: put that "
                                 'address in Settings > LibreNMS.', response=resp)
    return resp


def reset():
    with _lock:
        _down.update(until=0.0, base=None, why='')
