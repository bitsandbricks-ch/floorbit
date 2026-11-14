"""Widgets are data: a plugin returns a dict and Floorbit draws it (frontend/src/widgets/WidgetBody.tsx).

No plugin code runs in the browser, and text is always shown as text, never as HTML.
Shapes (each may also have ``sub``, a short line under it, and ``link``, a path on this site):

    {"type": "stat", "value": 42, "unit": "Mbit/s", "tone": "ok|warn|err|"}
    {"type": "status", "items": [{"label": "DNS", "state": "up|down|warn|unknown", "detail": "12 ms"}]}
    {"type": "list", "items": [{"label": "sw-a-01", "value": "3 errors", "tone": "warn"}]}
    {"type": "table", "columns": [{"key": "name", "label": "Name"}], "rows": [{"name": "..."}]}
    {"type": "sparkline", "points": [1, 3, 2], "value": 2, "unit": "%", "min": 0, "max": 100}
"""
TONES = ('', 'ok', 'warn', 'err')
STATES = ('up', 'down', 'warn', 'unknown')
MAX_ITEMS = 50
MAX_POINTS = 500


class WidgetError(ValueError):
    pass


def _text(value, limit=200):
    return '' if value is None else str(value)[:limit]


def _tone(value):
    value = value or ''
    if value not in TONES:
        raise WidgetError(f'tone must be one of {TONES}')
    return value


def _link(value):
    # Only paths on this site: a plugin can't send people to another host from the dashboard.
    value = _text(value, 300)
    return value if value.startswith('/') and not value.startswith('//') else ''


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WidgetError('numbers must be numbers')
    return value


def check_widget(raw, item):
    """A clean copy of what the plugin returned, or WidgetError."""
    if not isinstance(raw, dict):
        raise WidgetError('a widget is a dict')
    kind = raw.get('type')
    out = {'type': kind, 'id': item['id'], 'label': item.get('label', ''), 'size': item.get('size', 'small'),
           'refresh': item.get('refresh', 60), 'sub': _text(raw.get('sub')), 'link': _link(raw.get('link'))}
    if kind == 'stat':
        value = raw.get('value')
        out.update(value=value if isinstance(value, (int, float)) and not isinstance(value, bool) else _text(value, 40),
                   unit=_text(raw.get('unit'), 20), tone=_tone(raw.get('tone')))
    elif kind == 'status':
        items = []
        for i in (raw.get('items') or [])[:MAX_ITEMS]:
            state = i.get('state', 'unknown') if isinstance(i, dict) else None
            if state not in STATES:
                raise WidgetError(f'state must be one of {STATES}')
            items.append({'label': _text(i.get('label'), 80), 'state': state, 'detail': _text(i.get('detail'), 120)})
        out['items'] = items
    elif kind == 'list':
        out['items'] = [{'label': _text(i.get('label'), 80), 'value': _text(i.get('value'), 80),
                         'tone': _tone(i.get('tone'))}
                        for i in (raw.get('items') or [])[:MAX_ITEMS] if isinstance(i, dict)]
    elif kind == 'table':
        cols = [{'key': _text(c.get('key'), 40), 'label': _text(c.get('label') or c.get('key'), 40)}
                for c in (raw.get('columns') or [])[:12] if isinstance(c, dict) and c.get('key')]
        if not cols:
            raise WidgetError('a table needs columns')
        out['columns'] = cols
        out['rows'] = [{c['key']: _text(r.get(c['key']), 120) for c in cols}
                       for r in (raw.get('rows') or [])[:MAX_ITEMS] if isinstance(r, dict)]
    elif kind == 'sparkline':
        out['points'] = [_number(p) for p in (raw.get('points') or [])[-MAX_POINTS:]]
        for key in ('value', 'min', 'max'):
            if raw.get(key) is not None:
                out[key] = _number(raw[key])
        out['unit'] = _text(raw.get('unit'), 20)
    else:
        raise WidgetError('type must be stat, status, list, table or sparkline')
    return out
