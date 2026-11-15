"""Plugins: Settings > Plugins for admins, the dashboard, and the API plugins add.

Who may do what:

- Settings > Plugins and ``/api/settings/plugins/...`` (turn on and off, test, log): admins only,
  through the ``/settings`` and ``/api/settings`` path rules of the request guard.
- ``POST /api/plugins/<id>/actions/<action>``: the permission the action names (``permission:``,
  or the older ``role:`` mapped across; settings.manage when it names none). Every run is in the
  audit log, with parameter names, never values.
- ``GET /api/plugins/menu``: the plugins' entries for the floor plan's right-click menu
  (``context_menu:``), only those whose action this account may run.
- Widgets and endpoints: a signed-in account with the permission they name (floorplan.view by
  default). They are never open to the public, whatever ``AUTH_PUBLIC_READ`` says.
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import audit, spa
from ..plugins import SETTING_TYPES, PluginError

bp = Blueprint('plugins', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


def _user():
    from auth import current_user
    return current_user()


def _allowed(needed):
    """None when the signed-in account may, else the refusal to return."""
    auth = current_app.extensions.get('auth')
    if auth is None or not auth.enabled:
        return None   # sign-in switched off: everyone may do everything, as elsewhere
    from auth import roles
    user = _user()
    if not user:
        return jsonify({'error': 'Sign in required', 'login_url': '/login'}), 401
    if not roles.can(user, needed):
        return jsonify({'error': f"Your role can't do this. It needs: {roles.PERMISSIONS[needed]}.",
                        'permission_needed': needed}), 403
    return None


def _error(message, status=400):
    return jsonify({'error': message}), status


def _params(action, body):
    """The action's parameters from the request, checked against its params: list."""
    out = {}
    for f in action.get('params') or []:
        key, ftype = f['key'], f.get('type', 'string')
        raw = body.get(key, f.get('default'))
        if raw in (None, '') and f.get('required'):
            raise PluginError(f"{f.get('label') or key} is required")
        if raw is None:
            out[key] = None
            continue
        kind = SETTING_TYPES[ftype]
        if kind == 'bool':
            out[key] = raw is True or str(raw).lower() in ('1', 'true', 'yes', 'on')
        elif kind == 'int':
            try:
                out[key] = int(raw)
            except (TypeError, ValueError):
                raise PluginError(f"{f.get('label') or key} must be a whole number") from None
            if not f.get('min', -10 ** 12) <= out[key] <= f.get('max', 10 ** 12):
                raise PluginError(f"{f.get('label') or key} is out of range")
        elif kind == 'list':
            items = raw if isinstance(raw, list) else str(raw).split(',')
            out[key] = [str(i).strip()[:200] for i in items if str(i).strip()][:100]
        elif kind == 'choice':
            options = [str(o['value'] if isinstance(o, dict) else o) for o in f['options']]
            if str(raw) not in options:
                raise PluginError(f"{f.get('label') or key} must be one of {', '.join(options)}")
            out[key] = str(raw)
        else:
            out[key] = str(raw)[:2000]
    return out


# ── Admin: Settings > Plugins ─────────────────────────────────────────────────────────────

@bp.route('/settings/plugins')
def plugins_page():
    return spa.render('Plugins')


@bp.route('/api/settings/plugins', methods=['GET'])
def list_plugins():
    return jsonify({'plugins': _registry().as_list()})


@bp.route('/api/settings/plugins/<plugin_id>', methods=['PUT'])
def update_plugin(plugin_id):
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get('enabled'), bool):
        return _error('Send {"enabled": true} or {"enabled": false}')
    try:
        _registry().set_enabled(plugin_id, body['enabled'])
    except KeyError:
        return _error('No such plugin', 404)
    except PluginError as exc:
        return _error(str(exc))
    spec = _registry().specs[plugin_id]
    return jsonify({'plugins': _registry().as_list(), 'name': spec.name})


@bp.route('/api/settings/plugins/<plugin_id>/test', methods=['POST'])
def test_plugin(plugin_id):
    spec = _registry().active(plugin_id)
    if spec is None:
        return _error('Turn the plugin on first', 404)
    try:
        message = _registry().call(spec, 'test')
    except PluginError as exc:
        return jsonify({'ok': False, 'message': str(exc)})
    return jsonify({'ok': True, 'message': str(message or 'OK')[:500]})


@bp.route('/api/settings/plugins/<plugin_id>/log', methods=['GET'])
def plugin_log(plugin_id):
    if plugin_id not in _registry().specs:
        return _error('No such plugin', 404)
    return jsonify({'lines': _registry().logs.get(plugin_id)})


# ── Actions, widgets, endpoints ───────────────────────────────────────────────────────────

@bp.route('/api/plugins/<plugin_id>/actions/<action_id>', methods=['POST'])
def run_action(plugin_id, action_id):
    registry = _registry()
    spec = registry.active(plugin_id)
    action = spec.item('actions', action_id) if spec else None
    if action is None:
        return _error('No such action', 404)
    refused = _allowed(action['permission'])
    if refused:
        return refused
    body = request.get_json(silent=True) or {}
    user = (_user() or {}).get('username')
    try:
        params = _params(action, body)
    except PluginError as exc:   # refused before any plugin code ran: not logged, like other refusals
        return _error(str(exc))
    try:
        result = registry.call(spec, f'run_{action_id}', params)
    except PluginError as exc:
        audit.record('plugins', f"Ran {spec.name}: {action['label']}", user=user, target=spec.id,
                     fields=list(params) or None, ok=False)
        return _error(str(exc))
    audit.record('plugins', f"Ran {spec.name}: {action['label']}", user=user, target=spec.id, fields=list(params))
    result = result if isinstance(result, dict) else {'message': str(result or 'Done')}
    return jsonify({'ok': True, 'message': str(result.get('message') or 'Done')[:500],
                    'data': {k: v for k, v in result.items() if k != 'message'}})


@bp.route('/api/plugins/<plugin_id>/widgets/<widget_id>', methods=['GET'])
def widget(plugin_id, widget_id):
    spec = _registry().active(plugin_id)
    item = spec.item('widgets', widget_id) if spec else None
    if item is None:
        return _error('No such widget', 404)
    refused = _allowed(item['permission'])
    if refused:
        return refused
    try:
        return jsonify(_registry().widget(spec, widget_id))
    except PluginError as exc:
        return _error(str(exc), 502)


@bp.route('/api/plugins/<plugin_id>/endpoints/<endpoint_id>', methods=['GET'])
def endpoint(plugin_id, endpoint_id):
    spec = _registry().active(plugin_id)
    item = spec.item('endpoints', endpoint_id) if spec else None
    if item is None:
        return _error('No such endpoint', 404)
    refused = _allowed(item['permission'])
    if refused:
        return refused
    args = {k: v[:200] for k, v in list(request.args.items())[:20]}
    try:
        return jsonify(_registry().call(spec, f'endpoint_{endpoint_id}', args))
    except PluginError as exc:
        return _error(str(exc), 502)
    except TypeError:
        return _error('The plugin returned something that is not JSON', 502)


# ── Dashboard ─────────────────────────────────────────────────────────────────────────────

@bp.route('/dashboard')
def dashboard_page():
    return spa.render('Dashboard')


@bp.route('/api/plugins/menu', methods=['GET'])
def context_menu():
    """The plugins' entries for the floor plan's right-click menu that this account may run."""
    from auth import roles
    auth = current_app.extensions.get('auth')
    user = _user()
    if auth is None or not auth.enabled:
        granted = set(roles.PERMISSIONS)   # sign-in switched off: everyone may do everything
    else:
        granted = roles.permissions_of(roles.of(user)) if user else set()
    entries = []
    registry = _registry()
    for spec in registry.specs.values():
        if not registry.enabled(spec):
            continue
        for entry in spec.items('context_menu'):
            action = spec.item('actions', entry['action'])
            if action and action['permission'] in granted:
                entries.append({'plugin': spec.id, 'plugin_name': spec.name, 'label': entry['label'],
                                'targets': entry['targets'],
                                'danger': bool(action.get('danger')),
                                'url': f"/api/plugins/{spec.id}/actions/{action['id']}"})
    return jsonify({'entries': entries})


@bp.route('/api/dashboard', methods=['GET'])
def dashboard():
    refused = _allowed('floorplan.view')
    if refused:
        return refused
    from auth import roles
    user = _user()
    granted = roles.permissions_of(roles.of(user)) if user else set(roles.PERMISSIONS)
    tiles = []
    registry = _registry()
    for spec in registry.specs.values():
        if not registry.enabled(spec):
            continue
        for w in spec.items('widgets'):
            if w['permission'] in granted:
                tiles.append({'plugin': spec.id, 'plugin_name': spec.name, 'id': w['id'], 'label': w['label'],
                              'size': w.get('size', 'small'), 'refresh': w['refresh'],
                              'url': f"/api/plugins/{spec.id}/widgets/{w['id']}"})
        for a in spec.items('actions'):
            if a.get('dashboard') and a['permission'] in granted:
                tiles.append({'plugin': spec.id, 'plugin_name': spec.name, 'id': a['id'], 'label': a['label'],
                              'kind': 'action', 'danger': bool(a.get('danger')),
                              'url': f"/api/plugins/{spec.id}/actions/{a['id']}"})
    return jsonify({'tiles': tiles})


# Saved layouts (issue #103): which tiles a screen shows, in which order (floorbit/dashboard_layouts.py).
@bp.route('/api/dashboard/layouts', methods=['GET'])
def dashboard_layouts():
    refused = _allowed('floorplan.view')
    if refused:
        return refused
    from .. import dashboard_layouts as layouts
    return jsonify({'layouts': layouts.all_layouts()})


@bp.route('/api/dashboard/layouts/<layout_id>', methods=['PUT'])
def save_dashboard_layout(layout_id):
    from .. import dashboard_layouts as layouts
    user = _user() or {}
    try:
        layout = layouts.save(layout_id, request.get_json(silent=True) or {}, user.get('username'))
    except layouts.LayoutError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Saved dashboard layout', g.get('audit_user'), layout['name'])
    return jsonify(layout)


@bp.route('/api/dashboard/layouts/<layout_id>', methods=['DELETE'])
def delete_dashboard_layout(layout_id):
    from .. import dashboard_layouts as layouts
    try:
        layouts.delete(layout_id)
    except layouts.LayoutError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Removed dashboard layout', g.get('audit_user'), layout_id)
    return jsonify({'ok': True})
