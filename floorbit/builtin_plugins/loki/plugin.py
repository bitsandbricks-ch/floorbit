"""Grafana Loki: the syslog pushed for longer storage (``POST /loki/api/v1/push``) and searched
with LogQL (``GET /loki/api/v1/query_range``) on the Logs page.

Labels stay few, as Loki wants: job="floorbit", source="syslog", device, severity, and event when
set. The rest of a line is JSON, so ``| json`` in LogQL gets program, message, port and seat.
"""
import json
import re

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

BATCH = 1000
LABEL_VALUE = re.compile(r'[^\w.:/@-]')


def label(value):
    return LABEL_VALUE.sub('_', str(value or ''))[:64] or 'unknown'


def streams(lines, event=''):
    """Loki's push body for Floorbit's lines, grouped by their labels."""
    groups = {}
    for line in lines:
        labels = {'job': 'floorbit', 'source': 'syslog', 'device': label(line.get('device')),
                  'severity': label(line.get('severity'))}
        if event:
            labels['event'] = label(event)
        body = {k: line.get(k) for k in ('program', 'message', 'host', 'sender', 'port', 'seat') if line.get(k)}
        groups.setdefault(tuple(sorted(labels.items())), []).append(
            [str(int(line['ts'] * 1e9)), json.dumps(body, separators=(',', ':'))])
    return {'streams': [{'stream': dict(k), 'values': v} for k, v in groups.items()]}


def line_from(stream, ns, text):
    """One Loki result back in the shape of the Logs page."""
    try:
        body = json.loads(text)
        if not isinstance(body, dict):
            raise ValueError
    except ValueError:
        body = {'message': text}
    return {'id': int(ns) // 1000, 'ts': int(ns) / 1e9, 'severity': stream.get('severity') or 'info',
            'device': stream.get('device') or stream.get('host') or stream.get('job') or 'loki',
            'program': body.get('program'), 'message': str(body.get('message') or text)[:2048],
            'port': body.get('port'), 'seat': body.get('seat')}


class Plugin(Base):
    def _http(self):
        url = self.settings.get('url')
        if not url:
            raise PluginError('Set the Loki URL under Settings > Plugins.')
        auth = (self.settings.get('username') or '', self.settings.get('password') or '')
        headers = {'X-Scope-OrgID': self.settings['tenant']} if self.settings.get('tenant') else None
        return self.ctx.http(url, timeout=15, auth=auth if auth[0] else None, headers=headers)

    @staticmethod
    def _check(resp, what):
        if resp.status_code in (401, 403):
            raise PluginError('Loki refused the username or password.')
        if resp.status_code >= 400:
            text = (getattr(resp, 'text', '') or '').strip()[:200]
            raise PluginError(f'Loki answered {resp.status_code} to {what}' + (f': {text}' if text else '.'))

    def push_logs(self, lines):
        http = self._http()
        for i in range(0, len(lines), BATCH):
            resp = http.post('/loki/api/v1/push', json=streams(lines[i:i + BATCH], self.settings.get('event_label')))
            self._check(resp, 'the push')
        return len(lines)

    def query_logs(self, query, start, end, limit):
        resp = self._http().get('/loki/api/v1/query_range', params={
            'query': query, 'start': str(int(start * 1e9)), 'end': str(int(end * 1e9)), 'limit': limit,
            'direction': 'backward'})
        if resp.status_code == 400:
            text = (getattr(resp, 'text', '') or '').strip()[:300]
            raise PluginError(f'Loki can\'t read that query: {text}' if text else 'Loki can\'t read that query.')
        self._check(resp, 'the query')
        try:
            result = (resp.json().get('data') or {}).get('result') or []
        except (ValueError, AttributeError) as exc:
            raise PluginError("Loki's answer isn't JSON. Is the URL its HTTP API?") from exc
        out = [line_from(r.get('stream') or {}, ns, text) for r in result if isinstance(r, dict)
               for ns, text in (r.get('values') or [])]
        out.sort(key=lambda ln: -ln['ts'])
        return out[:limit]

    def test(self):
        resp = self._http().get('/loki/api/v1/labels')
        self._check(resp, 'the labels')
        return 'Connected: Loki answers.'
