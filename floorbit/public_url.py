"""Where the crew opens Floorbit, for links in alerts and messages (issue #1433, zero setup).

The Public URL setting still wins. Without it Floorbit remembers the address a signed-in crew
member last opened a page at, so Discord alerts, handovers and the agent's CA links work without
anyone typing the address in. Attendee pages (check-in through an agent's front door) never teach
it: the crew's address is what alerts link to.
"""
import threading

from integrations import config

from . import store

FILE = 'public_url.json'
# Calls and files, not pages someone opened: these may come from scripts or other names.
SKIP = ('/api/', '/static/', '/assets/', '/app/')
_lock = threading.Lock()
_known = {}     # tenant file -> the address last written, so a page view writes only on a change


def _path():
    return store.tenant_file(FILE)


def learned():
    """The address the crew last opened Floorbit at, '' before anyone did."""
    try:
        return str((store.read_json(_path(), {}) or {}).get('url') or '')
    except Exception as exc:  # noqa: BLE001  # a broken file only costs the fallback
        print(f'[public-url] could not read {FILE}: {exc}')
        return ''


def get():
    """The Public URL setting, else the learnt address; no slash at the end."""
    return str(config.get('PUBLIC_URL', '') or learned() or '').rstrip('/')


def learn(url):
    url = (url or '').rstrip('/')
    if not url.startswith(('http://', 'https://')) or len(url) > 200:
        return False
    path = _path()
    with _lock:
        if _known.get(path) == url:
            return False
        if learned() != url:
            store.write_json(path, {'url': url})
        _known[path] = url
    return True


def init_app(app):
    from flask import request

    @app.after_request
    def remember_where_the_crew_is(response):
        # A signed-in page view (not the API, not a public or attendee page) names the crew's address.
        try:
            if request.method == 'GET' and not request.path.startswith(SKIP) and _crew_request():
                learn(request.url_root)
        except Exception as exc:  # noqa: BLE001  # never break a page for this
            print(f'[public-url] {exc}')
        return response


def _crew_request():
    from flask import current_app

    from auth import current_user
    from integrations import checkin
    if checkin.attendee_ip():
        return False
    auth = current_app.extensions.get('auth')
    # Sign-in off: every page view is the crew's, as the request guard sees it.
    return bool(current_user()) or not (auth and auth.enabled)
