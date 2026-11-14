"""HTTP check: is each configured web service answering?"""
import time
from urllib.parse import urlsplit

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

STALE = 55   # seconds before the widget checks again on its own
SLOW_MS = 2000   # answering slower than this is amber on the health wall


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
                results.append({'name': t['name'], 'state': 'up' if ok else 'down', 'ms': ms,
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

    def _recent(self):
        last = self.ctx.state.get('last') or {}
        stale = time.time() - (last.get('at') or 0) > STALE
        return self._check_all() if stale else last.get('results') or []

    def health_checks(self):
        out = []
        for r in self._recent():
            status = r['state']
            if status == 'up' and (r.get('ms') or 0) > SLOW_MS:
                status = 'warn'
            metrics = [{'label': 'Answer time', 'value': r['ms'], 'unit': 'ms'}] if r.get('ms') is not None else []
            out.append({'id': r['name'].lower(), 'name': r['name'], 'kind': 'web', 'status': status,
                        'summary': r['detail'], 'metrics': metrics})
        return out

    def widget_services(self):
        results = self._recent()
        if not results:
            return {'type': 'status', 'items': [], 'sub': 'No services configured yet.'}
        return {'type': 'status',
                'items': [{'label': r['name'], 'state': r['state'], 'detail': r['detail']} for r in results],
                'sub': f"{sum(r['state'] == 'up' for r in results)} of {len(results)} up"}

    def endpoint_results(self, args):
        return self.ctx.state.get('last') or {'results': []}
