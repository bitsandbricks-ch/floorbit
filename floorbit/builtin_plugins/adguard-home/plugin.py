"""AdGuard Home: lookups from its query log (``GET /control/querylog``) for DNS analytics.

The log answers newest first, a page at a time; ``older_than`` asks for the page before. We read
back until we reach the time Floorbit asked for, at most PAGES pages a poll.
"""
from datetime import datetime

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

PAGE = 500
PAGES = 20
# Reasons AdGuard Home gives for an answer it blocked. Rewrites and safe search aren't blocks.
BLOCKED = {'FilteredBlackList', 'FilteredSafeBrowsing', 'FilteredParental', 'FilteredInvalid',
           'FilteredBlockedService'}


def parse_time(value):
    """AdGuard writes RFC 3339 with nanoseconds (2026-11-14T10:00:00.123456789+01:00)."""
    text = str(value or '').strip().replace('Z', '+00:00')
    if '.' in text:
        head, _, rest = text.partition('.')
        digits = ''.join(c for c in rest if c.isdigit())
        zone = rest[len(digits):]
        text = f'{head}.{digits[:6]}{zone}'
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def entry(row):
    ts = parse_time(row.get('time'))
    name = (row.get('question') or {}).get('name') if isinstance(row.get('question'), dict) else None
    if ts is None or not name:
        return None
    return {'ts': ts, 'domain': name, 'client': row.get('client') or '', 'blocked': row.get('reason') in BLOCKED}


class Plugin(Base):
    def _http(self):
        url = self.settings.get('url')
        if not url:
            raise PluginError('Set the AdGuard Home URL under Settings > Plugins.')
        auth = (self.settings.get('username') or '', self.settings.get('password') or '')
        return self.ctx.http(url, timeout=15, auth=auth if auth[0] else None)

    def _page(self, http, older_than=None):
        params = {'limit': PAGE}
        if older_than:
            params['older_than'] = older_than
        resp = http.get('/control/querylog', params=params)
        if resp.status_code in (401, 403):
            raise PluginError('AdGuard Home refused the username or password.')
        if resp.status_code >= 400:
            raise PluginError(f'AdGuard Home answered {resp.status_code}.')
        try:
            body = resp.json()
        except ValueError as exc:
            raise PluginError("AdGuard Home's answer isn't JSON. Is the URL its web interface?") from exc
        return body.get('data') or [], body.get('oldest') or ''

    def dns_queries(self, since):
        http = self._http()
        out, older_than = [], None
        for _ in range(PAGES):
            rows, oldest = self._page(http, older_than)
            done = False
            for row in rows:
                e = entry(row) if isinstance(row, dict) else None
                if e is None:
                    continue
                if e['ts'] <= since:
                    done = True
                    break
                out.append(e)
            if done or not rows or not oldest:
                break
            older_than = oldest
        return out

    def test(self):
        rows, _oldest = self._page(self._http())
        return f'Connected: the query log answers ({len(rows)} recent lookups).'
