"""HTTP check: is each configured web service answering?"""
import time
from urllib.parse import urlsplit

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

STALE = 55   # seconds before the widget checks again on its own


def parse_targets(raw):
    targets = []
    for item in raw or []:
        name, _, url = item.partition('=') if '=' in item.split('://')[0] else ('', '', item)
        url = url.strip()
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise PluginError(f'"{item}" is not an http:// or https:// URL')
        targets.append({'name': (name.strip() or parts.hostname)[:60], 'url': url})
    return targets


class Plugin(Base):
    def _check_all(self):
        targets = parse_targets(self.settings.get('targets'))
        http = self.ctx.http(timeout=self.settings.get('timeout') or 5)
        results = []
        for t in targets:
            started = time.monotonic()
            try:
                resp = http.get(t['url'])
                ms = int((time.monotonic() - started) * 1000)
                ok = resp.status_code < 400
                results.append({'name': t['name'], 'state': 'up' if ok else 'down',
                                'detail': f'{resp.status_code} in {ms} ms'})
            except PluginError as exc:
                results.append({'name': t['name'], 'state': 'down', 'detail': str(exc)[:120]})
        self.ctx.set_state('last', {'at': time.time(), 'results': results})
        return results

    def test(self):
        targets = parse_targets(self.settings.get('targets'))
        if not targets:
            raise PluginError('Add at least one service under Settings > Plugins.')
        return f'{len(targets)} service(s) configured.'

    def run_check(self, params):
        results = self._check_all()
        down = [r['name'] for r in results if r['state'] != 'up']
        if not results:
            return {'message': 'No services configured yet.'}
        message = f'{len(results) - len(down)} of {len(results)} up'
        return {'message': message + (f": {', '.join(down)} down" if down else '')}

    def widget_services(self):
        last = self.ctx.state.get('last') or {}
        stale = time.time() - (last.get('at') or 0) > STALE
        results = self._check_all() if stale else last.get('results') or []
        if not results:
            return {'type': 'status', 'items': [], 'sub': 'No services configured yet.'}
        return {'type': 'status',
                'items': [{'label': r['name'], 'state': r['state'], 'detail': r['detail']} for r in results],
                'sub': f"{sum(r['state'] == 'up' for r in results)} of {len(results)} up"}

    def endpoint_results(self, args):
        return self.ctx.state.get('last') or {'results': []}
