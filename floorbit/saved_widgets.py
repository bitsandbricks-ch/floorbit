"""Saved widgets (issue #1009): a tile pane with its sources and settings, kept under a name, for
any dashboard to show.

- **Widgets** are these saved ones; **Types** are the widget types they are drawn as (stat, gauge,
  bars, ... issue #894). A widget is made from a type, or copied from another widget.
- A dashboard pane of kind ``widget`` shows a saved widget and follows its changes. "Clone" in the
  pane settings copies it into that dashboard as a tile pane of its own, independent from then on.
- Everyone who may edit dashboards may edit widgets (``floorplan.edit``, Mike 2026-11-19).
- A widget a dashboard still shows can't be removed: clone it there first, or take it off.

Kept in data.json under ``widgets``; the pane is checked like a dashboard's tile pane
(dashboards._pane), so anything a tile pane can do, a widget can.
"""
import re
import threading
import time

from .store import load_data, save_data

KEY = 'widgets'
MAX_WIDGETS = 200
NAME_MAX = 60
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}\Z')
_lock = threading.Lock()


class WidgetError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def all_widgets(data=None):
    data = load_data() if data is None else data
    raw = data.get(KEY)
    return [w for w in raw if isinstance(w, dict) and w.get('id')] if isinstance(raw, list) else []


def by_id(data=None):
    """``{id: widget}``, for resolving the widget panes of many dashboards at once."""
    return {w['id']: w for w in all_widgets(data)}


def get(widget_id, data=None):
    return by_id(data).get(widget_id)


def _slug(name):
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:28] or 'widget'
    return base if base[0].isalnum() else f'w-{base}'[:28]


def _clean(body):
    from . import dashboards
    if not isinstance(body, dict):
        raise WidgetError('Send the widget as a JSON object.')
    name = ' '.join(str(body.get('name') or '').split())[:NAME_MAX]
    if not name:
        raise WidgetError('Give the widget a name.')
    raw = body.get('pane')
    if not isinstance(raw, dict):
        raise WidgetError('Pick what the widget shows.')
    try:
        # The name is the widget's title; a pane showing it may still set its own.
        pane = dashboards._pane({**raw, 'kind': 'tile', 'title': '', 'hide_title': False})
    except dashboards.LayoutError as exc:
        raise WidgetError(str(exc)) from exc
    return {'name': name, 'pane': pane}


def used_on(widget_id, data=None):
    """The names of the saved dashboards that show this widget."""
    from . import dashboards
    data = load_data() if data is None else data
    return [layout.get('name') or layout['id'] for layout in dashboards._saved(data)
            if any(p.get('kind') == 'widget' and p.get('widget') == widget_id for p in dashboards.layout_panes(layout))]


def save(widget_id, body, by):
    """Creates the widget (``widget_id`` None: an id from its name) or replaces it."""
    clean = _clean(body)
    with _lock:
        data = load_data()
        widgets = all_widgets(data)
        taken = {w['id'] for w in widgets}
        if widget_id is None:
            if len(widgets) >= MAX_WIDGETS:
                raise WidgetError(f'Floorbit keeps at most {MAX_WIDGETS} widgets.')
            base = _slug(clean['name'])
            widget_id, n = base, 2
            while widget_id in taken:
                widget_id, n = f'{base}-{n}', n + 1
        elif widget_id not in taken:
            raise WidgetError('No such widget.', 404)
        widget = {'id': widget_id, **clean, 'updated_at': time.time(), 'by': by}
        data[KEY] = [widget if w['id'] == widget_id else w for w in widgets] + ([] if widget_id in taken else [widget])
        save_data(data)
    return widget


def delete(widget_id):
    with _lock:
        data = load_data()
        widgets = all_widgets(data)
        if widget_id not in {w['id'] for w in widgets}:
            raise WidgetError('No such widget.', 404)
        shown = used_on(widget_id, data)
        if shown:
            raise WidgetError(f'{", ".join(shown)} still show this widget. Clone it there or take it off first.', 409)
        data[KEY] = [w for w in widgets if w['id'] != widget_id]
        save_data(data)
