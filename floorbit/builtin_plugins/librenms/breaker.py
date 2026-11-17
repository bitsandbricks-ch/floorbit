"""Every request to LibreNMS goes through ``get``: once LibreNMS doesn't answer, the next calls
fail at once for BREAK_FOR seconds instead of each waiting out its own timeout.

Without it a LibreNMS that hangs made pages that ask about many seats or switches wait minutes
(the heatmap asked 144 seats, ten seconds each). The status monitor keeps asking in the background
and notices when it is back.
"""
import threading
import time

import requests
from requests.adapters import HTTPAdapter

BREAK_FOR = 30   # seconds
_lock = threading.Lock()
_down = {'until': 0.0, 'base': None, 'why': ''}


# One connection pool: a seat lookup is three or four requests, and opening a new TLS connection
# for each cost LibreNMS more than answering them.
_session = requests.Session()
_session.mount('http://', HTTPAdapter(pool_connections=4, pool_maxsize=64))
_session.mount('https://', HTTPAdapter(pool_connections=4, pool_maxsize=64))
_send = _session.get     # the tests send through requests.get, which they replace


def _base(url):
    return '/'.join(str(url).split('/')[:3])   # scheme://host[:port]


def get(url, **kwargs):
    now = time.monotonic()
    base = _base(url)
    with _lock:
        if _down['base'] == base and now < _down['until']:
            raise requests.ConnectionError(f"LibreNMS did not answer a moment ago ({_down['why']})")
    try:
        return _send(url, **kwargs)
    except (requests.ConnectionError, requests.Timeout) as exc:
        with _lock:
            _down.update(until=time.monotonic() + BREAK_FOR, base=base, why=type(exc).__name__)
        raise


def reset():
    with _lock:
        _down.update(until=0.0, base=None, why='')
