"""Saved floor plan views: a hall shown a certain way, under a name, to open again or put on a screen.

A view keeps where the plan looks (``view``: x, y, w, h in drawing units), which layers are on and how
strong (``layers`` and ``fade``, the same text as the plan's address, frontend/src/pages/plan/layers.ts)
and the seat filter (``show``). Views are shared with the event's crew; a ``private`` one only shows to
whoever saved it. Saving needs ``floorplan.edit`` (auth/roles.py). Dashboard hall plans can show a view
or go through several (frontend/src/pages/dashboards/PlanPane.tsx).

Views belong to the event, in ``plan-views.json`` next to its plan: halls are the event's own.
"""
import re
import threading
import time
import uuid

from . import store

MAX_VIEWS = 200
NAME_MAX = 60
FILTERS = ('all', 'problems', 'offline', 'recent', 'note', 'checked_in')
# The layers' text from the plan's address: ids and "id:percent", nothing else.
LAYERS_RE = re.compile(r'^[a-z_]{1,20}(,[a-z_]{1,20}){0,30}$')
FADE_RE = re.compile(r'^[a-z_]{1,20}:\d{1,3}(,[a-z_]{1,20}:\d{1,3}){0,30}$')
REF_RE = re.compile(r'^[A-Za-z0-9_.:-]{1,80}$')

_lock = threading.Lock()


class ViewError(ValueError):
    """Raised with one of the fixed messages below; the API answers with ``public(exc)``."""


NO_NAME = 'A view needs a name'
LONG_NAME = f'A view name is at most {NAME_MAX} characters'
NO_HALL = 'Pick a hall.'
BAD_BOX = 'A view needs where the plan looks: x, y, width and height'
BAD_LAYERS = 'Layers are written like the plan address: ids separated by commas'
BAD_SHOW = f'Show is one of: {", ".join(FILTERS)}.'
TOO_MANY = f'At most {MAX_VIEWS} views: delete one first'
NAME_TAKEN = 'A view with this name exists already in this hall'
NOT_YOURS = 'Only the person who saved a private view can change it'
_MESSAGES = {m: m for m in (NO_NAME, LONG_NAME, NO_HALL, BAD_BOX, BAD_LAYERS, BAD_SHOW, TOO_MANY, NAME_TAKEN,
                            NOT_YOURS)}


def public(exc):
    """The answer for ``exc``: its fixed message, looked up rather than read from the exception."""
    return _MESSAGES.get(exc.args[0] if exc.args else None, 'The view is not valid')


def _path():
    return store.event_path('plan-views.json')


def _all():
    found = store.read_json(_path(), {})
    views = found.get('views')
    return [v for v in views if isinstance(v, dict) and v.get('id')] if isinstance(views, list) else []


def visible(user, hall=None):
    """The views ``user`` sees (shared ones and their own private ones), of one hall or all."""
    return [v for v in _all()
            if (not v.get('private') or v.get('by') == user) and (hall is None or v.get('hall') == hall)]


def get(view_id, user):
    return next((v for v in visible(user) if v['id'] == view_id), None)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or abs(value) > 1e7:
        raise ViewError(BAD_BOX)
    return round(float(value), 2)


def clean(body):
    """The fields of a view from a request body; raises :class:`ViewError`."""
    name = str(body.get('name') or '').strip()
    if not name:
        raise ViewError(NO_NAME)
    if len(name) > NAME_MAX:
        raise ViewError(LONG_NAME)
    hall = str(body.get('hall') or '').strip()
    if not REF_RE.match(hall):
        raise ViewError(NO_HALL)
    box = body.get('view')
    if not isinstance(box, dict):
        raise ViewError(BAD_BOX)
    view = {k: _number(box.get(k)) for k in ('x', 'y', 'w', 'h')}
    if view['w'] <= 0 or view['h'] <= 0:
        raise ViewError(BAD_BOX)
    layers = body.get('layers')
    fade = str(body.get('fade') or '')
    if layers is not None and not (isinstance(layers, str) and (layers == '' or LAYERS_RE.match(layers))):
        raise ViewError(BAD_LAYERS)
    if fade and not FADE_RE.match(fade):
        raise ViewError(BAD_LAYERS)
    show = body.get('show') or 'all'
    if show not in FILTERS:
        raise ViewError(BAD_SHOW)
    out = {'name': name, 'hall': hall, 'view': view, 'show': show, 'private': bool(body.get('private'))}
    if layers is not None:
        out['layers'] = layers   # missing: the plan's default layers
    if fade:
        out['fade'] = fade
    return out


def _taken(views, fields, but=None):
    name = fields['name'].lower()
    return any(v['id'] != but and v.get('hall') == fields['hall'] and str(v.get('name', '')).lower() == name
               and (not v.get('private') or v.get('by') == fields.get('by')) for v in views)


def add(body, user):
    fields = clean(body)
    with _lock:
        views = _all()
        if len(views) >= MAX_VIEWS:
            raise ViewError(TOO_MANY)
        fields['by'] = user
        if _taken(views, fields):
            raise ViewError(NAME_TAKEN)
        view = {'id': uuid.uuid4().hex[:12], **fields, 'saved': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        store.write_json(_path(), {'views': [*views, view]})
    return view


def update(view_id, body, user):
    fields = clean(body)
    with _lock:
        views = _all()
        old = next((v for v in views if v['id'] == view_id and (not v.get('private') or v.get('by') == user)), None)
        if old is None:
            raise KeyError(view_id)
        if old.get('private') and old.get('by') != user:
            raise ViewError(NOT_YOURS)
        new = {**old, **fields, 'by': old.get('by'), 'saved': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        if fields['private'] and old.get('by') != user:
            raise ViewError(NOT_YOURS)   # making someone else's shared view your private one
        if _taken(views, new, but=view_id):
            raise ViewError(NAME_TAKEN)
        if 'layers' not in fields:
            new.pop('layers', None)
        if 'fade' not in fields:
            new.pop('fade', None)
        store.write_json(_path(), {'views': [new if v['id'] == view_id else v for v in views]})
    return new


def delete(view_id, user):
    with _lock:
        views = _all()
        left = [v for v in views if not (v['id'] == view_id and (not v.get('private') or v.get('by') == user))]
        if len(left) == len(views):
            raise KeyError(view_id)
        store.write_json(_path(), {'views': left})


def shared(ids):
    """The shared views among ``ids``, as a public screen may see them: where they look and their seat
    filter, without who saved them or their layers (a public pane draws the public layers only)."""
    wanted = set(ids)
    return [{k: v[k] for k in ('id', 'name', 'hall', 'view', 'show') if k in v}
            for v in _all() if v['id'] in wanted and not v.get('private')]
