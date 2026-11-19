"""Widgets are data: a plugin returns a dict and Floorbit draws it (frontend/src/widgets/WidgetBody.tsx).

No plugin code runs in the browser, and text is always shown as text, never as HTML.
Shapes (each may also have ``sub``, a short line under it, and ``link``, a path on this site):

    {"type": "stat", "value": 42, "unit": "Mbit/s", "tone": "ok|warn|err|", "min": 0, "max": 100}
    {"type": "status", "items": [{"label": "DNS", "state": "up|down|warn|unknown", "detail": "12 ms"}]}
    {"type": "list", "items": [{"label": "sw-a-01", "value": "3 errors", "tone": "warn", "number": 3, "max": 48}]}
    {"type": "table", "columns": [{"key": "name", "label": "Name"}], "rows": [{"name": "..."}]}
    {"type": "sparkline", "points": [1, 3, 2], "value": 2, "unit": "%", "min": 0, "max": 100}
    {"type": "series", "unit": "bit/s", "series": [{"label": "Download", "points": [[1763560000, 4.2e9], ...]}]}

``min`` and ``max`` on a stat let it show as a gauge; ``number`` (and ``max``) on list items let a
list show as bars or a pie. All of them are optional.

A ``series`` is up to four lines over time: each point is ``[unix seconds, value]``, oldest first.
The dashboard's graph widget draws it with a crosshair that names each line's value on hover.
"""
import math

TONES = ('', 'ok', 'warn', 'err')
STATES = ('up', 'down', 'warn', 'unknown')
MAX_ITEMS = 50
MAX_POINTS = 500
MAX_SERIES = 4
MAX_MARKS = 50


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


def _finite(value):
    # NaN and infinity aren't JSON: the browser couldn't read the answer at all.
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and (isinstance(value, int) or math.isfinite(value)))


def _number(value):
    if not _finite(value):
        raise WidgetError('numbers must be finite numbers')
    return value


def _numbers(raw, out, keys):
    """Copies the optional numbers ``keys`` from ``raw`` into ``out``."""
    for key in keys:
        if raw.get(key) is not None:
            out[key] = _number(raw[key])
    return out


def _list(raw, key):
    value = raw.get(key) or []
    if not isinstance(value, list):
        raise WidgetError(f'{key} must be a list')
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
        out.update(value=value if _finite(value) else _text(value, 40),
                   unit=_text(raw.get('unit'), 20), tone=_tone(raw.get('tone')))
        _numbers(raw, out, ('min', 'max'))
    elif kind == 'status':
        items = []
        for i in _list(raw, 'items')[:MAX_ITEMS]:
            state = i.get('state', 'unknown') if isinstance(i, dict) else None
            if state not in STATES:
                raise WidgetError(f'state must be one of {STATES}')
            items.append({'label': _text(i.get('label'), 80), 'state': state, 'detail': _text(i.get('detail'), 120)})
        out['items'] = items
    elif kind == 'list':
        items = []
        for i in _list(raw, 'items')[:MAX_ITEMS]:
            if isinstance(i, dict):
                item = {'label': _text(i.get('label'), 80), 'value': _text(i.get('value'), 80),
                        'tone': _tone(i.get('tone'))}
                items.append(_numbers(i, item, ('number', 'max')))
        out['items'] = items
    elif kind == 'table':
        cols = [{'key': _text(c.get('key'), 40), 'label': _text(c.get('label') or c.get('key'), 40)}
                for c in _list(raw, 'columns')[:12] if isinstance(c, dict) and c.get('key')]
        if not cols:
            raise WidgetError('a table needs columns')
        out['columns'] = cols
        out['rows'] = [{c['key']: _text(r.get(c['key']), 120) for c in cols}
                       for r in _list(raw, 'rows')[:MAX_ITEMS] if isinstance(r, dict)]
    elif kind == 'sparkline':
        out['points'] = [_number(p) for p in _list(raw, 'points')[-MAX_POINTS:]]
        _numbers(raw, out, ('value', 'min', 'max'))
        out['unit'] = _text(raw.get('unit'), 20)
    elif kind == 'series':
        lines = []
        for line in _list(raw, 'series')[:MAX_SERIES]:
            if not isinstance(line, dict):
                raise WidgetError('a series is a dict with label and points')
            points = []
            for p in _list(line, 'points')[-MAX_POINTS:]:
                if not (isinstance(p, (list, tuple)) and len(p) == 2):
                    raise WidgetError('a series point is [time, value]')
                points.append([_number(p[0]), _number(p[1])])
            # ``ghost``: a line for comparison (yesterday, the last event), drawn dashed and faint.
            entry = {'label': _text(line.get('label'), 40), 'points': points}
            if line.get('ghost'):
                entry['ghost'] = True
            lines.append(entry)
        out['series'] = lines
        out['unit'] = _text(raw.get('unit'), 20)
        # ``marks``: what happened when (a switch down, an incident), drawn as lines across the graph.
        marks = []
        for m in _list(raw, 'marks')[-MAX_MARKS:]:
            if not isinstance(m, dict):
                raise WidgetError('a mark is a dict with t, label and tone')
            marks.append({'t': _number(m.get('t')), 'label': _text(m.get('label'), 80),
                          'tone': _tone(m.get('tone') or '')})
        if marks:
            out['marks'] = marks
    else:
        raise WidgetError('type must be stat, status, list, table, sparkline or series')
    return out
