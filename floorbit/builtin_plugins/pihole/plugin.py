"""Pi-hole 6: lookups from its query log (``GET /api/queries``) for DNS analytics.

Each poll signs in (``POST /api/auth``), reads the lookups since the time Floorbit asked for, a
page at a time, and signs out again: Pi-hole allows only a few sessions at once.
"""
import contextlib
import time

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

PAGE = 1000
PAGES = 20
# Statuses for lookups Pi-hole blocked (its gravity lists, regex and deny lists, or upstream).
BLOCKED = {'GRAVITY', 'REGEX', 'DENYLIST', 'GRAVITY_CNAME', 'REGEX_CNAME', 'DENYLIST_CNAME',
           'EXTERNAL_BLOCKED_IP', 'EXTERNAL_BLOCKED_NULL', 'EXTERNAL_BLOCKED_NXRA', 'EXTERNAL_BLOCKED_EDE15',
           'SPECIAL_DOMAIN'}


def entry(row):
    try:
        ts = float(row.get('time'))
    except (TypeError, ValueError):
        return None
    client = row.get('client')
    client = client.get('ip') if isinstance(client, dict) else client
    if not row.get('domain'):
        return None
    return {'ts': ts, 'domain': row['domain'], 'client': client or '', 'blocked': row.get('status') in BLOCKED}


class Plugin(Base):
    def _http(self):
        url = self.settings.get('url')
        if not url:
            raise PluginError('Set the Pi-hole URL under Settings > Plugins.')
        return self.ctx.http(url, timeout=15)

    def _json(self, resp, what):
        if resp.status_code in (401, 403):
            raise PluginError('Pi-hole refused the password.')
        if resp.status_code >= 400:
            raise PluginError(f'Pi-hole answered {resp.status_code} for {what}.')
        try:
            return resp.json()
        except ValueError as exc:
            raise PluginError("Pi-hole's answer isn't JSON. Is it Pi-hole 6 or newer?") from exc

    def _signed_in(self, work):
        http = self._http()
        session = self._json(http.post('/api/auth', json={'password': self.settings.get('password') or ''}),
                             'the sign-in').get('session') or {}
        if not session.get('valid') or not session.get('sid'):
            raise PluginError('Pi-hole refused the password.')
        http.s.headers['X-FTL-SID'] = session['sid']
        try:
            return work(http)
        finally:
            with contextlib.suppress(PluginError):   # the session runs out by itself
                http.request('DELETE', '/api/auth')

    def dns_queries(self, since):
        until = time.time()

        def read(http):
            out = []
            for page in range(PAGES):
                body = self._json(http.get('/api/queries', params={
                    'from': int(since), 'until': int(until) + 1, 'length': PAGE, 'start': page * PAGE}), 'the lookups')
                rows = body.get('queries') or []
                out += [e for e in (entry(r) for r in rows if isinstance(r, dict)) if e and e['ts'] > since]
                if len(rows) < PAGE:
                    break
            return out

        return self._signed_in(read)

    def test(self):
        def ask(http):
            body = self._json(http.get('/api/queries', params={'length': 1}), 'the lookups')
            return body.get('recordsTotal')

        total = self._signed_in(ask)
        return 'Connected: the query log answers' + (f' ({total} lookups kept).' if total is not None else '.')
