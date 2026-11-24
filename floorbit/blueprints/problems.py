"""The Problems page and alert mutes (issue #10). See docs/alerts.md.

- ``GET /problems``: everything wrong right now.
- ``GET /api/problems``: the list (floorbit/problems.py), with the running mutes. For people who
  see the incident board, a problem carries the id of its open incident (issue #278): one made from
  it (issue #882), or for an offline switch any open one on that switch.
- ``GET /problems/<id>``, ``GET /api/problems/<id>``: one problem's page (issue #882): the problem,
  its open incident and where to look next. 404 once it is over. A security finding's page also
  carries the ``finding`` (evidence, uplink) for ``seats.view``, and whether its port can be shut
  (issue #885).
- ``POST /api/alerts/mutes``: ``{"switch_id", "minutes", "reason"}`` mutes a switch's alerts;
  ``{"service_id", ...}`` mutes a service on the health wall instead (issue #256), ``{"ap", ...}``
  a Wi-Fi access point (issue #1064), ``{"problem_id", ...}`` any other problem on the list (issue #887).
- ``PATCH /api/alerts/mutes/<id>``: ``{"minutes"}`` makes a running mute last longer (issue #264).
- ``DELETE /api/alerts/mutes/<id>``: ends a mute (a switch id, ``health:<service id>`` or ``wifi:<ap>``).
Mutes need ``incidents.work`` (auth/roles.py): the people working problems decide what pages them.
"""
from flask import Blueprint, current_app, g, jsonify, request

from integrations import alerting, events

from .. import audit, i18n, incidents, inventory, problems, spa, wifi
from ..store import load_data

bp = Blueprint('problems', __name__)


def _user():
    from auth import current_user  # late: auth imports floorbit while it loads
    return current_user()


def _can(permission):
    from auth import roles
    if not current_app.extensions['auth'].enabled:
        return True
    user = _user()
    return bool(user and roles.can(user, permission))


@bp.route('/problems')
def problems_page():
    return spa.render('Problems')


@bp.route('/api/problems', methods=['GET'])
def list_problems():
    body = {**problems.current(_can('seats.view')), 'can_mute': _can('incidents.work')}
    # Titles and places in the reader's language (issue #467); names, ports and plugin texts stay.
    lang = i18n.language(request.headers.get('Accept-Language'))
    for key in ('problems', 'attention'):
        body[key] = [{**p, 'title': i18n.translate(p.get('title'), lang),
                      'where': i18n.translate(p.get('where'), lang)} for p in body.get(key) or []]
    # An offline switch can become an incident in one click, or links the one already open (issue #278).
    body['can_report'] = not current_app.extensions['auth'].enabled or incidents.can_see_board(_user())
    if body['can_report']:
        _incidents(body['problems'] + body['attention'])
    return jsonify(body)


def _incidents(items):
    """Each problem's open incident: one made from it, or for an offline switch any on the switch."""
    open_for, made_from = {}, {}
    for incident in incidents.list_all():
        if incident.get('status') == 'fixed':
            continue
        if incident.get('switch_id'):
            open_for.setdefault(incident['switch_id'], incident['id'])
        if incident.get('from_problem'):
            made_from.setdefault(incident['from_problem'], incident['id'])
    for p in items:
        found = made_from.get(p['id']) or (open_for.get(p.get('switch_id')) if p.get('kind') == 'switch' else None)
        p['incident'] = found


@bp.route('/problems/<path:problem_id>')
def problem_page(problem_id):
    return spa.render('Problem')


@bp.route('/api/problems/<path:problem_id>', methods=['GET'])
def one_problem(problem_id):
    may_see_people = _can('seats.view')
    found = problems.find(may_see_people, problem_id)
    if found is None:
        return jsonify({'error': 'This problem is over.'}), 404
    lang = i18n.language(request.headers.get('Accept-Language'))
    found = {**found, 'title': i18n.translate(found.get('title'), lang),
             'where': i18n.translate(found.get('where'), lang)}
    can_report = not current_app.extensions['auth'].enabled or incidents.can_see_board(_user())
    if can_report:
        _incidents([found])
    # Where to look next: the device's page, the seat on the plan, its logs and machines.
    device = None
    if found.get('device'):
        device = next(({'id': d['id'], 'name': d['name']} for d in inventory.devices(load_data(), include_hidden=True)
                       if d['name'] == found['device']), None)
    body = {'problem': found, 'device': device, 'can_mute': _can('incidents.work'),
            'can_report': can_report, 'may_see_people': may_see_people}
    if found['kind'] == 'security' and may_see_people:
        body.update(_finding(found['id'][len('security:'):]))
    return jsonify(body)


def _finding(finding_id):
    """A security finding as its problem page shows it: what the plugin saw, and the port."""
    from .. import ports, security, uplink_guard
    f = security.get(finding_id)
    if not f:
        return {}
    uplink = uplink_guard.reason(f['switch'], f['port'], load_data()) if f.get('switch') and f.get('port') else None
    info = ports.info(current_app.extensions['floorbit_plugins']) if _can('ports.act') else {'available': False}
    keep = ('id', 'kind', 'severity', 'detail', 'evidence', 'switch', 'port', 'seat', 'mac', 'ip',
            'plugin', 'plugin_name', 'first_seen', 'last_seen')
    return {'finding': {**{k: f.get(k) for k in keep}, 'uplink': uplink},
            'can_shut': bool(info.get('available')), 'needs_login': bool(info.get('needs_login'))}


@bp.route('/api/alerts/mutes', methods=['POST'])
def add_mute():
    body = request.get_json(silent=True) or {}
    if body.get('service_id'):
        wall = current_app.extensions.get('floorbit_health')
        check = next((c for c in (wall.snapshot()['checks'] if wall else []) if c['id'] == body['service_id']), None)
        if not check:
            return jsonify({'error': 'There is no such service.'}), 400
        key, name, label = alerting.service_key(check['id']), check['name'], 'Muted service alerts'
    elif body.get('problem_id'):
        # Any other problem, by its id on the list: it stays there, marked, and leaves the counts.
        found = problems.find(_can('seats.view'), str(body['problem_id']))
        if not found or not str(found.get('mute_id') or '').startswith(problems.PROBLEM_MUTE):
            return jsonify({'error': 'There is no such problem.'}), 400
        key, name, label = found['mute_id'], found.get('title') or found['id'], 'Muted a problem'
    elif body.get('ap'):
        # An access point from the Wi-Fi view (floorbit/wifi.py): only one it knows now.
        registry = current_app.extensions['floorbit_plugins']
        ap = next((a for a in wifi.ask(registry)[0] if a['name'].lower() == str(body['ap']).lower()), None)
        if not ap:
            return jsonify({'error': 'There is no such access point.'}), 400
        key, name, label = wifi.mute_key(ap['name']), ap['name'], 'Muted access point alerts'
    else:
        device = next((d for d in inventory.devices(load_data(), include_hidden=True)
                       if d['id'] == body.get('switch_id')), None)
        if not device:
            return jsonify({'error': 'There is no such switch.'}), 400
        key, name, label = device['id'], device['name'], 'Muted switch alerts'
    try:
        mute = alerting.mute(key, name, body.get('minutes'), g.get('audit_user'), body.get('reason'))
    except alerting.MuteError as exc:
        return jsonify({'error': str(exc)}), 400
    audit.record('alerts', label, user=g.get('audit_user'), target=name)
    events.publish('alerts.changed', {})
    return jsonify({'switch_id': key, **mute}), 201


@bp.route('/api/alerts/mutes/<path:switch_id>', methods=['PATCH'])
def extend_mute(switch_id):
    try:
        found = alerting.extend(switch_id, (request.get_json(silent=True) or {}).get('minutes'))
    except alerting.MuteError as exc:
        return jsonify({'error': str(exc)}), 400
    if not found:
        return jsonify({'error': 'That switch is not muted.'}), 404
    audit.record('alerts', 'Extended mute', user=g.get('audit_user'), target=found.get('name'))
    events.publish('alerts.changed', {})
    return jsonify({'switch_id': switch_id, **found})


@bp.route('/api/alerts/mutes/<path:switch_id>', methods=['DELETE'])
def end_mute(switch_id):
    found = alerting.unmute(switch_id)
    if not found:
        return jsonify({'error': 'That switch is not muted.'}), 404
    audit.record('alerts', 'Ended mute', user=g.get('audit_user'), target=found.get('name'))
    events.publish('alerts.changed', {})
    return jsonify({'ok': True})
