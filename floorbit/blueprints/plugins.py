"""Plugins: Settings > Plugins for admins, the dashboard, and the API plugins add.

Who may do what:

- Settings > Plugins and ``/api/settings/plugins/...`` (turn on and off, test, log): admins only,
  through the ``/settings`` and ``/api/settings`` path rules of the request guard.
- ``POST /api/plugins/<id>/actions/<action>``: the permission the action names (``permission:``,
  or the older ``role:`` mapped across; settings.manage when it names none). Every run is in the
  audit log, with parameter names, never values.
- ``GET /api/plugins/menu``: the plugins' entries for the floor plan's right-click menu
  (``context_menu:``), only those whose action this account may run.
- Widgets, panels and endpoints: a signed-in account with the permission they name (floorplan.view by
  default). They are never open to the public, whatever ``AUTH_PUBLIC_READ`` says.
"""
import json

from flask import Blueprint, current_app, jsonify, request

from .. import audit, i18n, spa
from .. import dashboard_core as core
from ..plugins import PANEL_TARGET_MAX, PANEL_TARGETS, SETTING_TYPES, PluginError
from ..plugins.widgets import check_widget

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


def _language():
    return i18n.language(request.headers.get('Accept-Language'))


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
            except (TypeError, ValueError, OverflowError):   # Overflow: JSON allows Infinity
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


@bp.route('/settings/plugins/<plugin_id>')
def plugin_page(plugin_id):
    return spa.render('Plugins')


@bp.route('/api/settings/plugins', methods=['GET'])
def list_plugins():
    return jsonify({'plugins': _registry().as_list(_language())})


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
    if spec.agent:
        # The agents pull it within a minute anyway; this only saves the wait.
        from .. import agent_plugins
        agent_plugins.reload_agents()
    return jsonify({'plugins': _registry().as_list(_language()),
                    'name': _registry().text(spec, spec.name, _language())})


@bp.route('/api/settings/plugins/<plugin_id>/test', methods=['POST'])
def test_plugin(plugin_id):
    spec = _registry().active(plugin_id)
    if spec is None:
        return _error('Turn the plugin on first', 404)
    from .. import agent_link
    try:
        if _registry().reaches_lan(spec) and not agent_link.may_call_here(spec):
            # It runs on the agent, so that is where its test has to run: this server can't reach it.
            message = agent_link.tunnel.call('plugin_test', [spec.id], timeout=20)
        else:
            message = _registry().call(spec, 'test')
    except (PluginError, agent_link.AgentError, agent_link.AgentUnavailable) as exc:
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
    if not isinstance(body, dict):
        return _error('Expected a JSON object')
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
        return _error(registry.text(spec, str(exc), _language()))
    audit.record('plugins', f"Ran {spec.name}: {action['label']}", user=user, target=spec.id, fields=list(params))
    result = result if isinstance(result, dict) else {'message': str(result or 'Done')}
    message = registry.text(spec, str(result.get('message') or 'Done'), _language())
    try:
        data = json.loads(json.dumps({k: v for k, v in result.items() if k != 'message'}, allow_nan=False))
    except (TypeError, ValueError, RecursionError):
        # It ran, so the answer is still "done"; only the extra data the browser couldn't read is dropped.
        registry.log(spec.id, f'action {action_id}: the data it returned is not JSON and was left out')
        data = {}
    return jsonify({'ok': True, 'message': message[:500], 'data': data})


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
        body = _registry().widget(spec, widget_id)
    except PluginError as exc:
        return _error(_registry().text(spec, str(exc), _language()), 502)
    return jsonify(german_widget(body, _language(), spec))


def _granted():
    """The permissions of whoever asks (every one when sign-in is off)."""
    from auth import roles
    auth = current_app.extensions.get('auth')
    if auth is None or not auth.enabled:
        return set(roles.PERMISSIONS)
    user = _user()
    return roles.permissions_of(roles.of(user)) if user else set()


@bp.route('/api/plugins/panels', methods=['GET'])
def panels():
    """The plugins' boxes for a seat, switch or device side panel that this account may see."""
    on = request.args.get('on', '')
    if on not in PANEL_TARGETS:
        return _error(f"on: one of {', '.join(PANEL_TARGETS)}")
    refused = _allowed('floorplan.view')
    if refused:
        return refused
    granted, registry, lang = _granted(), _registry(), _language()
    out = []
    for spec in registry.specs.values():
        if not registry.enabled(spec):
            continue
        for p in spec.items('panels'):
            if p['for'] == on and p['permission'] in granted:
                out.append({'plugin': spec.id, 'plugin_name': registry.text(spec, spec.name, lang),
                            'icon': spec.manifest.get('icon') or '', 'id': p['id'],
                            'label': registry.text(spec, p['label'], lang), 'refresh': p['refresh'],
                            'url': f"/api/plugins/{spec.id}/panels/{p['id']}"})
    return jsonify({'panels': out})


@bp.route('/api/plugins/<plugin_id>/panels/<panel_id>', methods=['GET'])
def panel(plugin_id, panel_id):
    spec = _registry().active(plugin_id)
    item = spec.item('panels', panel_id) if spec else None
    if item is None:
        return _error('No such panel', 404)
    refused = _allowed(item['permission'])
    if refused:
        return refused
    target = request.args.get('target', '')
    # A seat, switch or device id: short and printable, whatever the plugin then does with it.
    if not 0 < len(target) <= PANEL_TARGET_MAX or not target.isprintable():
        return _error('target: the id of the seat, switch or device')
    try:
        body = _registry().panel(spec, panel_id, target)
    except PluginError as exc:
        return _error(_registry().text(spec, str(exc), _language()), 502)
    return jsonify(german_widget(body, _language(), spec))


@bp.route('/plugins/<plugin_id>/<page_id>')
def plugin_own_page(plugin_id, page_id):
    return spa.render('Plugin')


def plugin_pages(lang):
    """The plugins' sidebar pages this account may open, as /api/pages lists pages."""
    granted, registry, out = _granted(), _registry(), []
    for spec in registry.specs.values():
        if not registry.enabled(spec):
            continue
        for item in spec.items('pages'):
            if item['permission'] in granted:
                out.append({'href': f"/plugins/{spec.id}/{item['id']}", 'id': f"plugin:{spec.id}:{item['id']}",
                            'label': registry.text(spec, item['label'], lang), 'icon': spec.manifest.get('icon') or '',
                            'plugin': registry.text(spec, spec.name, lang)})
    return out


@bp.route('/api/plugins/<plugin_id>/pages/<page_id>', methods=['GET'])
def plugin_page_tiles(plugin_id, page_id):
    """One plugin page: its widgets and actions this account may see, in the manifest's order."""
    spec = _registry().active(plugin_id)
    item = spec.item('pages', page_id) if spec else None
    if item is None:
        return _error('No such page', 404)
    refused = _allowed(item['permission'])
    if refused:
        return refused
    granted, registry, lang = _granted(), _registry(), _language()
    name = registry.text(spec, spec.name, lang)
    tiles = []
    for wid in item.get('widgets') or []:
        w = spec.item('widgets', wid)
        if w['permission'] in granted:
            tiles.append({'plugin': spec.id, 'plugin_name': name, 'id': wid,
                          'label': registry.text(spec, w['label'], lang),
                          'size': w.get('size', 'small'), 'refresh': w['refresh'],
                          'url': f'/api/plugins/{spec.id}/widgets/{wid}'})
    for aid in item.get('actions') or []:
        a = spec.item('actions', aid)
        if a['permission'] in granted:
            tiles.append({'plugin': spec.id, 'plugin_name': name, 'id': aid,
                          'label': registry.text(spec, a['label'], lang),
                          'kind': 'action', 'danger': bool(a.get('danger')),
                          'url': f'/api/plugins/{spec.id}/actions/{aid}'})
    return jsonify({'plugin': spec.id, 'plugin_name': name, 'icon': spec.manifest.get('icon') or '', 'id': page_id,
                    'label': registry.text(spec, item['label'], lang), 'columns': item['columns'], 'tiles': tiles})


@bp.route('/api/plugins/layers', methods=['GET'])
def layers():
    """The plugins' floor plan layers this account may see."""
    refused = _allowed('floorplan.view')
    if refused:
        return refused
    granted, registry, lang = _granted(), _registry(), _language()
    out = []
    for spec in registry.specs.values():
        if not registry.enabled(spec):
            continue
        for item in spec.items('layers'):
            if item['permission'] in granted:
                out.append({'plugin': spec.id, 'plugin_name': registry.text(spec, spec.name, lang),
                            'icon': spec.manifest.get('icon') or '', 'id': item['id'],
                            'label': registry.text(spec, item['label'], lang), 'refresh': item['refresh'],
                            'url': f"/api/plugins/{spec.id}/layers/{item['id']}"})
    return jsonify({'layers': out})


@bp.route('/api/plugins/<plugin_id>/layers/<layer_id>', methods=['GET'])
def layer(plugin_id, layer_id):
    spec = _registry().active(plugin_id)
    item = spec.item('layers', layer_id) if spec else None
    if item is None:
        return _error('No such layer', 404)
    refused = _allowed(item['permission'])
    if refused:
        return refused
    registry, lang = _registry(), _language()
    try:
        body = registry.layer(spec, layer_id)
    except PluginError as exc:
        return _error(registry.text(spec, str(exc), lang), 502)
    for entry in (*body['seats'].values(), *body['legend']):
        entry['label'] = registry.text(spec, entry['label'], lang)
    return jsonify(body)


def german_widget(body, lang, spec=None):
    """A plugin widget's own texts in ``lang``: from the plugin's locales/de-CH.json, else where
    Floorbit's catalog knows them, like the Health page does for the same checks ("GET … failed:
    …"). Values (names, numbers, hosts) stay."""
    if lang == 'en' or not isinstance(body, dict):
        return body

    def tr(text):
        return _registry().text(spec, text, lang) if spec is not None else i18n.translate(text, lang)
    out = {**body, **{k: tr(body[k]) for k in ('label', 'sub', 'unit') if isinstance(body.get(k), str)}}
    if isinstance(body.get('items'), list):
        out['items'] = [{**i, **{k: tr(i[k]) for k in ('label', 'detail') if isinstance(i.get(k), str)}}
                        if isinstance(i, dict) else i for i in body['items']]
    if isinstance(body.get('columns'), list):
        out['columns'] = [{**c, 'label': tr(c.get('label'))} if isinstance(c, dict) else c for c in body['columns']]
    return out


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
        value = _registry().timed(spec, f'endpoint_{endpoint_id}', args)
        # allow_nan=False: NaN or infinity would make an answer no browser can read.
        body = json.dumps(value, allow_nan=False, separators=(',', ':'))
    except PluginError as exc:
        return _error(str(exc), 502)
    except (TypeError, ValueError, RecursionError):
        _registry().log(spec.id, f'endpoint {endpoint_id}: the answer is not JSON')
        return _error('The plugin returned something that is not JSON', 502)
    return current_app.response_class(body + '\n', mimetype='application/json')



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
                entries.append({'plugin': spec.id, 'plugin_name': registry.text(spec, spec.name, _language()),
                                'label': registry.text(spec, entry['label'], _language()),
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
                tiles.append({'plugin': spec.id, 'plugin_name': spec.name, 'spec': spec, 'id': w['id'],
                              'label': w['label'],
                              'size': w.get('size', 'small'), 'refresh': w['refresh'],
                              'url': f"/api/plugins/{spec.id}/widgets/{w['id']}"})
        for a in spec.items('actions'):
            if a.get('dashboard') and a['permission'] in granted:
                tiles.append({'plugin': spec.id, 'plugin_name': spec.name, 'spec': spec, 'id': a['id'],
                              'label': a['label'],
                              'kind': 'action', 'danger': bool(a.get('danger')),
                              'url': f"/api/plugins/{spec.id}/actions/{a['id']}"})
    lang = i18n.language(request.headers.get('Accept-Language'))
    tiles = [{**{k: v for k, v in t.items() if k != 'spec'}, 'label': registry.text(t['spec'], t['label'], lang),
              'plugin_name': registry.text(t['spec'], t['plugin_name'], lang)}
             for t in tiles]
    # Floorbit's own tiles first: they work with no plugin set up (issue #302).
    from .. import features
    off = features.off()
    return jsonify({'tiles': core.tiles(_lang(), _may_see_board(user), lambda f: f not in off) + tiles})


def _lang():
    return request.accept_languages.best_match(['en', 'de'], default='en')


def _may_see_board(user):
    from .. import incidents
    return not current_app.extensions['auth'].enabled or incidents.can_see_board(user)


def _problems_tile(user):
    from auth import roles
    may_see_people = not current_app.extensions['auth'].enabled or bool(user and roles.can(user, 'seats.view'))
    return core.problems_widget(_lang(), may_see_people)


def _incidents_tile(user):
    return core.incidents_widget(_lang()) if _may_see_board(user) else None


def _switches_tile(user):
    return core.switches_widget(_lang(), current_app.extensions['floorbit_integrations']['monitor'].counts())


def _seats_tile(user):
    from .. import incidents
    from ..store import load_data
    from .stats_wall import online_seats
    online, _last = online_seats()
    seats = set(incidents.seat_numbers(load_data()))
    return core.seats_widget(_lang(), None if online is None else len(online & seats), len(seats))


def _seats_by_block_tile(user):
    from .. import seat_names
    from ..store import load_data
    from .stats_wall import online_seats
    online, _last = online_seats()
    blocks = {}
    for block in load_data().get('seat_blocks') or []:
        # A block named by its rows has no name: it shows as its row letters (#1078).
        name = seat_names.label(block)
        if name:
            blocks.setdefault(name, set()).update(s.upper() for s in seat_names.seats(block))
    return core.seats_by_block_widget(_lang(), blocks, online)


def _seats_by_row_tile(user):
    from .. import seat_names
    from ..store import load_data
    from .stats_wall import online_seats
    online, _last = online_seats()
    return core.seats_by_row_widget(_lang(), seat_names.hall_rows(load_data()), online)


def _down_tile(user):
    return core.down_widget(_lang(), current_app.extensions['floorbit_integrations']['monitor'].statuses)


def _switch_states_tile(user):
    return core.switch_states_widget(_lang(), current_app.extensions['floorbit_integrations']['monitor'].statuses)


def _open_incidents_tile(user):
    return core.open_incidents_widget(_lang()) if _may_see_board(user) else None


def _traffic_tile(user):
    # A pane's time range and comparison come as ?range= and ?compare= (dashboards._display).
    stats = current_app.extensions['floorbit_stats']
    rng = request.args.get('range') if request.args.get('range') in core.RANGES else None
    compare = request.args.get('compare') if request.args.get('compare') in core.COMPARES else None
    event = stats.event() if rng == 'event' or compare or request.args.get('marks') else None
    widget = core.traffic_widget(_lang(), stats.snapshot(), rng, compare, event['hours'] if event else ())
    if request.args.get('marks') == '1':
        from .. import incidents
        # Incidents only for those who may see the board, like the incident tiles.
        found = incidents.list_all() if _may_see_board(user) else ()
        core.with_marks(widget, core.event_marks(_lang(), event['switch_events'], found))
    return widget


def _snapshot():
    return current_app.extensions['floorbit_stats'].snapshot()


def _flows(user):
    """The flow summary as /api/flows gives it to this account, anomalies in its language."""
    from .. import i18n
    from .flows import _can, current, public
    snap = current()
    if not snap:
        return None
    out = public(snap, _can('seats.view'))
    lang = _lang()
    if lang != 'en':
        found = out.get('anomalies') or []
        out = {**out, 'anomalies': [{**a, 'title': i18n.log_text(a.get('title'), lang),
                                     'detail': i18n.log_text(a.get('detail'), lang)} for a in found]}
    return out


def _health():
    from .health import _wall, _with_mutes
    return _with_mutes(_wall().fresh())


def _services():
    from .. import services
    return services.overview()


def _lancache():
    from .. import agent_plugins
    from ..lancache import overview
    return overview(current_app.extensions.get('floorbit_lancache'), agent_plugins.health_of('lancache'))


def _power():
    from .power import _watch
    return _watch().snapshot()


def _agents():
    from .. import agent_link
    return [{**a, 'outdated': agent_link.outdated(a.get('protocol'))} for a in agent_link.all_agents()]


def _dns():
    dns = current_app.extensions.get('floorbit_dns')
    return dns.snapshot(core.DNS_HOURS) if dns else None


def _games():
    from .. import features, games
    from .flows import current
    ext = current_app.extensions
    return games.insights(ext.get('floorbit_dns') if features.on('dns') else None,
                          current() if features.on('traffic') else None, ext.get('floorbit_lancache'), core.DNS_HOURS)


def _wifi():
    from .. import wifi
    from ..store import load_data
    return wifi.overview(_registry(), load_data())


# Floorbit's own tiles (dashboard_core.TILES): one builder each, None when this account may not see it.
CORE_TILES = {'problems': _problems_tile, 'incidents': _incidents_tile, 'switches': _switches_tile,
              'seats': _seats_tile, 'down': _down_tile, 'switch_states': _switch_states_tile,
              'open_incidents': _open_incidents_tile, 'traffic': _traffic_tile,
              'seats_by_block': _seats_by_block_tile,
              'seats_by_row': _seats_by_row_tile,
              'bandwidth': lambda user: core.bandwidth_widget(_lang(), _snapshot()),
              'peak': lambda user: core.peak_widget(_lang(), _snapshot()),
              'ports': lambda user: core.ports_widget(_lang(), _snapshot()),
              'uplinks': lambda user: core.uplinks_widget(_lang(), _snapshot()),
              'top_ports': lambda user: core.top_ports_widget(_lang(), _snapshot()),
              'traffic_mix': lambda user: core.traffic_mix_widget(_lang(), _flows(user)),
              'flow_services': lambda user: core.flow_services_widget(_lang(), _flows(user)),
              'traffic_areas': lambda user: core.traffic_areas_widget(_lang(), _flows(user)),
              'anomalies': lambda user: core.anomalies_widget(_lang(), _flows(user)),
              'service_health': lambda user: core.service_health_widget(_lang(), _health()),
              'internet_uplinks': lambda user: core.internet_uplinks_widget(_lang(), _services()),
              'lancache': lambda user: core.lancache_widget(_lang(), _lancache()),
              'power_circuits': lambda user: core.power_circuits_widget(_lang(), _power()),
              'agents': lambda user: core.agents_widget(_lang(), _agents()),
              'dns_lookups': lambda user: core.dns_lookups_widget(_lang(), _dns()),
              'dns_sites': lambda user: core.dns_sites_widget(_lang(), _dns()),
              'dns_blocked': lambda user: core.dns_blocked_widget(_lang(), _dns()),
              'launchers': lambda user: core.launchers_widget(_lang(), _games()),
              'wifi_clients': lambda user: core.wifi_clients_widget(_lang(), _wifi()),
              'wifi_aps': lambda user: core.wifi_aps_widget(_lang(), _wifi())}


@bp.route('/api/dashboard/floorbit/<tile>', methods=['GET'])
def core_widget(tile):
    refused = _allowed('floorplan.view')
    if refused:
        return refused
    from .. import features
    build = CORE_TILES.get(tile)
    feature = core.TILES.get(tile, {}).get('feature')
    widget = build(_user()) if build and not (feature and not features.on(feature)) else None
    if widget is None:
        return _error('No such widget', 404)
    spec = core.TILES[tile]
    return jsonify(check_widget(widget, {'id': tile, 'label': '', 'size': spec['size'], 'refresh': spec['refresh']}))


