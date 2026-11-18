"""The tenant's events and which one a request works on (issue #466). Rules in floorbit/tenancy.py.

- Every request works on the event in the ``floorbit_event`` cookie, else the live one. ``?event=<id>``
  on any page picks one and remembers it in the cookie (kiosk and public pages use the query).
  The answer says which in ``X-Floorbit-Event``.
- ``GET /api/tenant/events``: the events, which is live and which this request is on.
- ``PUT /api/tenant/current`` ``{"event": "<id>"}``: work on that event from now on (anyone who
  sees the floor plan); ``{"event": null}`` follows the live one again.
- ``POST /api/tenant/events`` ``{"name": "...", "copy_from": "<id>"}``: a new event in planning.
- ``PATCH /api/tenant/events/<id>`` ``{"name": "...", "status": "live"}``: rename, make live, close.
  Admins only, like the rest of the event's settings.
- ``POST /api/tenant/events/<id>/copy`` ``{"to": "<id>", "parts": [...], "mode": "merge", "preview": true}``:
  copy parts of this event's floor plan into another one; with ``preview``, only say what would
  change. Admins only (floorbit/event_copy.py).

Changing the network from an event that isn't live (port actions, switch commands, the terminal,
RCON) is refused: those always reach the live event's network.
"""
from flask import Blueprint, current_app, g, jsonify, request

from integrations import events

from .. import audit, event_copy, store, tenancy

bp = Blueprint('tenant_events', __name__)

COOKIE = 'floorbit_event'
COOKIE_AGE = 30 * 24 * 3600
WRITE = ('POST', 'PUT', 'PATCH', 'DELETE')
# (path prefix, methods or None for all): what acts on the live network.
LIVE_ONLY = (
    ('/api/ports', WRITE),
    ('/api/commands', WRITE),
    ('/api/terminal', None),
    ('/api/game-servers/rcon', WRITE),
)


def _picked():
    """The event the request asks for: ?event=, then the cookie. None: the live one."""
    asked = request.args.get('event') or request.cookies.get(COOKIE)
    if not asked:
        return None
    return tenancy.find(asked)


def _live_only(path, method):
    return any((path == p or path.startswith(p + '/')) and (methods is None or method in methods)
               for p, methods in LIVE_ONLY)


def init_app(app):
    """Before every other hook but sign-in, so nothing reads an event's documents before the
    request's event is picked (called from create_app, right after init_auth)."""
    app.before_request(pick_event)
    app.after_request(remember_event)
    app.teardown_request(forget_event)


def pick_event():
    event = _picked()
    g.tenant_event_token = None
    if event is not None and event['status'] != 'live':
        g.tenant_event_token = store._event_dir.set(event['folder'])
    g.tenant_event = event or tenancy.live()
    if g.tenant_event['status'] != 'live' and _live_only(request.path, request.method):
        return jsonify({'error': "This event isn't live: switch to the live event to change the network."}), 409
    return None


def remember_event(response):
    event = getattr(g, 'tenant_event', None)
    if event is not None:
        response.headers['X-Floorbit-Event'] = event['id']
        if request.args.get('event') and tenancy.find(request.args['event']):
            response.set_cookie(COOKIE, event['id'], max_age=COOKIE_AGE, samesite='Lax',
                                secure=request.is_secure, httponly=True)
    return response


def forget_event(_exc):
    token = g.pop('tenant_event_token', None)
    if token is not None:
        store._event_dir.reset(token)


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _public(event):
    out = {k: v for k, v in event.items() if k != 'folder'}
    if not out.get('name') and event['id'] == tenancy.FIRST_EVENT:
        # The first event was named in the theme settings before events had names of their own.
        out['name'] = current_app.extensions['floorbit_settings'].get('theme.name') or ''
    return out


def _listing():
    return {'events': [_public(e) for e in tenancy.events()],
            'live': tenancy.live()['id'], 'current': g.tenant_event['id']}


@bp.route('/api/tenant/events', methods=['GET'])
def list_events():
    return jsonify(_listing())


@bp.route('/api/tenant/current', methods=['PUT'])
def pick():
    body = request.get_json(silent=True) or {}
    wanted = body.get('event')
    response = jsonify({'ok': True})
    if wanted is None:
        response.delete_cookie(COOKIE)
        return response
    event = tenancy.find(wanted) if isinstance(wanted, str) else None
    if event is None:
        return jsonify({'error': 'No such event.'}), 404
    response.set_cookie(COOKIE, event['id'], max_age=COOKIE_AGE, samesite='Lax',
                        secure=request.is_secure, httponly=True)
    return response


@bp.route('/api/tenant/events', methods=['POST'])
def create():
    body = request.get_json(silent=True) or {}
    try:
        event = tenancy.create(body.get('name'), copy_from=body.get('copy_from') or None)
    except tenancy.EventError as exc:
        return _error(exc)
    audit.record('events', 'Added an event', user=g.get('audit_user'), target=event['id'])
    events.publish('tenant_events', {})
    return jsonify({'event': {k: v for k, v in event.items() if k != 'folder'}}), 201


@bp.route('/api/tenant/events/<event_id>', methods=['PATCH'])
def change(event_id):
    body = request.get_json(silent=True) or {}
    try:
        event = tenancy.update(event_id, name=body.get('name'), status=body.get('status'))
    except tenancy.EventError as exc:
        return _error(exc)
    action = 'Made an event live' if body.get('status') == 'live' else 'Changed an event'
    audit.record('events', action, user=g.get('audit_user'), target=event_id,
                 fields=[k for k in ('name', 'status') if k in body])
    events.publish('tenant_events', {})
    return jsonify({'event': {k: v for k, v in event.items() if k != 'folder'}})


@bp.route('/api/tenant/events/<event_id>/copy', methods=['POST'])
def copy(event_id):
    body = request.get_json(silent=True) or {}
    args = (event_id, body.get('to'), body.get('parts'), body.get('mode') or 'merge')
    try:
        if body.get('preview'):
            return jsonify({'changes': event_copy.preview(*args), 'parts': list(event_copy.PARTS)})
        changes = event_copy.copy(*args)
    except event_copy.CopyError as exc:
        return _error(exc)
    audit.record('events', "Copied an event's plan", user=g.get('audit_user'),
                 target=f"{event_id} -> {body.get('to')}", fields=list(changes))
    events.publish('tenant_events', {})
    return jsonify({'changes': changes})
