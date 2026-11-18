"""VictoriaLogs: the syslog pushed for longer storage (``POST /insert/jsonline``) and searched with
LogsQL (``GET /select/logsql/query``) on the Logs page. The same job as the Loki plugin, for the
VictoriaLogs that docker-compose.yml starts with ``--profile logs``.

Streams stay few (job and device); severity, program, port and seat are fields, so LogsQL filters
on them directly: ``severity:warning seat:B-3``.
"""
import json
from datetime import UTC, datetime

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

BATCH = 1000
FIELDS = ('severity', 'program', 'host', 'sender', 'port', 'seat')


def _iso(ts):
    return datetime.fromtimestamp(float(ts), tz=UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def jsonlines(lines, event=''):
    """VictoriaLogs' JSON-lines body for Floorbit's lines."""
    out = []
    for line in lines:
        row = {'_time': _iso(line['ts']), '_msg': str(line.get('message') or ''), 'job': 'floorbit',
               'source': 'syslog', 'device': str(line.get('device') or 'unknown')[:64]}
        row.update({k: str(line[k]) for k in FIELDS if line.get(k)})
        if event:
            row['event'] = str(event)[:64]
        out.append(json.dumps(row, separators=(',', ':')))
    return '\n'.join(out).encode() + b'\n'


def _ts(value):
    try:
        text = str(value).replace('Z', '+00:00')
        # VictoriaLogs writes nanoseconds; Python's parser takes at most microseconds.
        if '.' in text:
            head, rest = text.split('.', 1)
            digits = len(rest) - len(rest.lstrip('0123456789'))
            text = head + '.' + rest[:min(digits, 6)] + rest[digits:]
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return 0.0


def line_from(row):
    """One VictoriaLogs result back in the shape of the Logs page."""
    ts = _ts(row.get('_time'))
    return {'id': int(ts * 1e6), 'ts': ts, 'severity': row.get('severity') or 'info',
            'device': row.get('device') or row.get('host') or row.get('job') or 'victorialogs',
            'program': row.get('program'), 'message': str(row.get('_msg') or '')[:2048],
            'port': row.get('port'), 'seat': row.get('seat')}


class Plugin(Base):
    def _http(self):
        url = self.settings.get('url')
        if not url:
            raise PluginError('Set the VictoriaLogs URL under Settings > Plugins.')
        auth = (self.settings.get('username') or '', self.settings.get('password') or '')
        headers = {}
        account = (self.settings.get('account') or '').strip()
        if account:
            acc, _, project = account.partition(':')
            headers = {'AccountID': acc.strip() or '0', 'ProjectID': project.strip() or '0'}
        return self.ctx.http(url, timeout=15, auth=auth if auth[0] else None, headers=headers or None)

    @staticmethod
    def _check(resp, what):
        if resp.status_code in (401, 403):
            raise PluginError('VictoriaLogs refused the username or password.')
        if resp.status_code >= 400:
            text = (getattr(resp, 'text', '') or '').strip()[:200]
            raise PluginError(f'VictoriaLogs answered {resp.status_code} to {what}' + (f': {text}' if text else '.'))

    def push_logs(self, lines):
        http = self._http()
        event = self.settings.get('event_label')
        for i in range(0, len(lines), BATCH):
            resp = http.post('/insert/jsonline', data=jsonlines(lines[i:i + BATCH], event),
                             params={'_stream_fields': 'job,device', '_msg_field': '_msg', '_time_field': '_time'},
                             headers={'Content-Type': 'application/stream+json'})
            self._check(resp, 'the push')
        return len(lines)

    def query_logs(self, query, start, end, limit):
        resp = self._http().get('/select/logsql/query', params={
            'query': query or '*', 'start': str(int(start)), 'end': str(int(end)), 'limit': limit})
        if resp.status_code == 400:
            text = (getattr(resp, 'text', '') or '').strip()[:300]
            raise PluginError(f'VictoriaLogs can\'t read that query: {text}' if text
                              else 'VictoriaLogs can\'t read that query.')
        self._check(resp, 'the query')
        text = getattr(resp, 'text', '') or ''
        if text.strip() and not text.lstrip().startswith('{'):
            raise PluginError("VictoriaLogs' answer isn't JSON lines. Is the URL its HTTP address?")
        out = []
        for raw in text.splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(line_from(row))
        out.sort(key=lambda ln: -ln['ts'])
        return out[:limit]

    def test(self):
        resp = self._http().get('/select/logsql/query', params={'query': '*', 'limit': 1})
        self._check(resp, 'a test query')
        return 'Connected: VictoriaLogs answers.'
