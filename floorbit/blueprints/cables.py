"""Cables and patching (issue #97). The rules live in floorbit/cables.py.

- ``GET /cables``: the page (React); ``/cables/<id>`` is one cable's page (what its labels' QR links to),
  ``/cables/new`` adds one.
- ``GET /api/cables?q=&seat=``: the cables, and whether a plugin can import them.
- ``POST /api/cables``, ``PATCH /api/cables/<id>``, ``DELETE /api/cables/<id>``: the crew's own cables.
- ``POST /api/cables/import``: read the cables from NetBox again (replaces the last import).
- ``GET /api/cables/check``: the cables to seats against the port watch's last read (patch_check.py).
- ``GET /api/cables/clients?read=1``: clients on seat ports that the cables don't explain, from the
  switches' MAC tables (port_clients.py). Needs ``seats.view``: it names MACs and IPs.
- ``GET /cables/walk``, ``GET /api/cables/walk?switch=&since=``: walking the row; the ports that
  came up since the walk began (walk.py).
- ``POST /api/cables/assign``: ``{"seat", "switch", "port", "swap"}``: the seat is on that port.
- ``POST /api/cables/block``: patch a whole seat block to a switch (issue #473). With ``dry_run``
  it only says which seat gets which port and what is in the way; ``replace`` moves the crew's
  cables that are in the way.
- ``GET /api/cables/labels.pdf?ids=&q=``: two labels per cable to print. ``GET /api/cables.csv``.

Reading needs ``floorplan.view``, changing ``floorplan.edit`` (auth/roles.py).
"""
import math
import time

from flask import Blueprint, Response, current_app, g, jsonify, request

from integrations import events

from .. import agent_link, audit, cables, patch_check, port_areas, port_clients, spa, syslog, walk

bp = Blueprint('cables', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _audit(action, cable, fields=None):
    audit.record('cables', action, g.get('audit_user'), f"{cable['label']}: {cables.route(cable)}", fields)


def _error(exc):
    return jsonify({'error': str(exc), **getattr(exc, 'extra', {})}), getattr(exc, 'status', 400)


def _picked():
    rows = cables.all_cables()
    ids = set(filter(None, (request.args.get('ids') or '').split(','))) or None
    rows = cables.matching(rows, request.args.get('q'), ids)
    seat = (request.args.get('seat') or '').strip().upper()
    return [c for c in rows if c.get('seat') == seat] if seat else rows


@bp.route('/cables')
def cables_page():
    return spa.render('Cables')


@bp.route('/cables/<cable_id>')
def cable_page(cable_id):
    return spa.render('Cable')


@bp.route('/api/cables', methods=['GET'])
def list_cables():
    sources = [s.name for s in cables.sources(_registry())]
    if agent_link.active():
        sources.append('Local agent')
    return jsonify({'cables': _picked(), 'sources': sources})


@bp.route('/api/cables', methods=['POST'])
def add_cable():
    try:
        cable = cables.add(request.get_json(silent=True) or {}, _who())
    except cables.CableError as exc:
        return _error(exc)
    _audit('Added cable', cable)
    events.publish('cables.changed', {'id': cable['id']})
    return jsonify(cable), 201


@bp.route('/api/cables/<cable_id>', methods=['PATCH'])
def update_cable(cable_id):
    try:
        body = request.get_json(silent=True) or {}
        cable = cables.update(cable_id, body, _who())
    except cables.CableError as exc:
        return _error(exc)
    _audit('Changed cable', cable, [f for f in body if f in cables.FIELDS])
    events.publish('cables.changed', {'id': cable_id})
    return jsonify(cable)


@bp.route('/api/cables/<cable_id>', methods=['DELETE'])
def delete_cable(cable_id):
    cable = next((c for c in cables.all_cables() if c['id'] == cable_id), None)
    if not cable or not cables.delete(cable_id):
        return jsonify({'error': 'No such cable.'}), 404
    _audit('Removed cable', cable)
    events.publish('cables.changed', {'id': cable_id})
    return jsonify({'ok': True})


@bp.route('/api/cables/import', methods=['POST'])
def import_cables():
    if not cables.sources(_registry()) and not agent_link.active():
        return jsonify({'error': 'No plugin that is on can tell Floorbit about cables. Turn on NetBox first.'}), 409
    try:
        count, errors = cables.import_from(_registry(), _who())
    except cables.CableError as exc:
        audit.record('cables', 'Imported cables', g.get('audit_user'), 'NetBox', ok=False)
        return _error(exc)
    audit.record('cables', f'Imported {count} cables', g.get('audit_user'), 'NetBox')
    events.publish('cables.changed', {})
    return jsonify({'imported': count, 'errors': errors})


@bp.route('/api/cables/check', methods=['GET'])
def check_cables():
    watch = current_app.extensions.get('floorbit_attention')
    if watch is None or not watch.last_poll:
        return jsonify({'last_poll': None, 'blocks': [], 'missing': {'count': 0, 'rows': []},
                        'down': {'count': 0, 'rows': []}, 'unplanned': {'count': 0, 'rows': []},
                        'conflicts': {'count': 0, 'rows': []}, 'unread': []})
    return jsonify({'last_poll': watch.last_poll, **patch_check.check(watch.port_reads, watch.read_switches)})


@bp.route('/api/cables/clients', methods=['GET'])
def port_clients_view():
    """The last read of the seat switches' MAC tables, against the cables (floorbit/port_clients.py).
    ``?read=1`` starts a new read in the background (at most every two minutes)."""
    finder = current_app.extensions['floorbit_port_clients']
    started = finder.request() if request.args.get('read') == '1' else False
    return jsonify({**port_clients.without_cabled(finder.state()), 'started': started})


@bp.route('/cables/walk')
def walk_page():
    return spa.render('Walk the row')


@bp.route('/api/cables/walk', methods=['GET'])
def walk_ups():
    """Ports of ``switch`` that came up since ``since`` (walk.py). Without ``since`` the walk begins
    now: the answer's ``since`` is what to send next, in the server's clock, not the phone's."""
    switch = (request.args.get('switch') or '').strip()[:80]
    if not switch:
        return jsonify({'error': 'Name the switch.'}), 400
    try:
        since = float(request.args.get('since') or 0) or time.time()
    except ValueError:
        since = time.time()
    if not math.isfinite(since):      # "nan" came back as a bare NaN no browser parses
        since = time.time()
    listening = syslog.settings()['enabled'] or agent_link.active()
    receiver = current_app.extensions.get('floorbit_syslog') if listening else None
    areas = port_areas.all_areas()
    ups = [{**u, 'area': port_areas.hint(switch, u['port'], areas)} for u in walk.walks.ups(switch, since, receiver)]
    return jsonify({'ups': ups, 'syslog': receiver is not None, 'since': since})


@bp.route('/api/cables/assign', methods=['POST'])
def assign_seat():
    """This seat is on that port: move its cable there, or make one (cables.assign)."""
    body = request.get_json(silent=True) or {}
    try:
        result = cables.assign(body, _who())
    except cables.CableError as exc:
        return _error(exc)
    _audit(f"Seat {result['cable']['seat']} found on its port"
           + (f" (swapped with {result['other_seat']})" if result['other_seat'] else ''), result['cable'])
    if result['changed']:
        events.publish('cables.changed', {})
    return jsonify(result)


@bp.route('/api/cables/block', methods=['POST'])
def patch_block():
    body = request.get_json(silent=True) or {}
    try:
        if body.get('dry_run'):
            return jsonify(cables.plan_block(body))
        plan, removed = cables.add_block(body, _who(), replace=bool(body.get('replace')))
    except cables.CableError as exc:
        return _error(exc)
    made = plan['cables']
    if made:
        audit.record('cables', f"Patched block {plan['block'] or '?'}", g.get('audit_user'),
                     f"{len(made)} seats to {made[0]['switch']} {made[0]['port']}-{made[-1]['port']}"
                     + (f', replaced {removed} cables' if removed else ''))
        events.publish('cables.changed', {})
    return jsonify({**plan, 'created': len(made), 'removed': removed})


@bp.route('/api/cables/labels.pdf', methods=['GET'])
def labels():
    # Behind a reverse proxy PUBLIC_URL is the address phones reach; else the one this request came in on.
    base = (current_app.extensions['auth'].public_url() or '').rstrip('/') or request.host_url.rstrip('/')
    headers = {'Content-Disposition': 'inline; filename="cable-labels.pdf"', 'Cache-Control': 'no-store'}
    return Response(cables.labels_pdf(_picked(), base), mimetype='application/pdf', headers=headers)


@bp.route('/api/cables.csv', methods=['GET'])
def csv_export():
    headers = {'Content-Disposition': 'attachment; filename="cables.csv"', 'Cache-Control': 'no-store'}
    return Response(cables.csv_text(_picked()), mimetype='text/csv', headers=headers)


# ── Rough port areas (floorbit/port_areas.py) ─────────────────────────────────
@bp.route('/api/port-areas', methods=['GET'])
def list_port_areas():
    return jsonify({'areas': sorted(port_areas.all_areas(), key=lambda a: (a['switch'].lower(), a['first']))})


@bp.route('/api/port-areas/batch', methods=['POST'])
def port_areas_batch():
    """``{"switch", "size": 10, "first_port": 1, "count", "starts": ["A-1", "A-11", "", ...],
    "dry_run"}``: one area per batch of ports, in place of what the switch had."""
    from .. import incidents
    body = request.get_json(silent=True) or {}
    try:
        areas = port_areas.quick_entry(body.get('switch'), body.get('starts'), body.get('size', 10),
                                       body.get('first_port', 1), body.get('count'),
                                       known=incidents.seat_numbers())
        if body.get('dry_run'):
            return jsonify({'areas': areas})
        made = port_areas.replace_switch(str(body['switch']).strip(), areas, by=_who())
    except port_areas.AreaError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('cables', 'Saved port areas', g.get('audit_user'),
                 f"{made[0]['switch']}: {', '.join(a['label'] for a in made)}")
    return jsonify({'areas': made})


@bp.route('/api/port-areas/<area_id>', methods=['DELETE'])
def delete_port_area(area_id):
    area = next((a for a in port_areas.all_areas() if a['id'] == area_id), None)
    if not area or not port_areas.delete(area_id=area_id):
        return jsonify({'error': 'No such port area.'}), 404
    audit.record('cables', 'Removed port area', g.get('audit_user'), f"{area['switch']}: {area['label']}")
    return jsonify({'ok': True})


@bp.route('/api/port-areas', methods=['DELETE'])
def delete_switch_port_areas():
    switch = (request.args.get('switch') or '').strip()
    if not switch:
        return jsonify({'error': 'Name the switch.'}), 400
    deleted = port_areas.delete(switch=switch)
    if deleted:
        audit.record('cables', 'Removed port areas', g.get('audit_user'), switch)
    return jsonify({'deleted': deleted})


@bp.route('/api/port-areas/lookup', methods=['GET'])
def port_area_lookup():
    """The likely area of a port (``switch`` + ``port``), or of the port an ``ip`` is on."""
    switch, port = request.args.get('switch'), request.args.get('port')
    ip = (request.args.get('ip') or '').strip()
    if ip and not (switch and port):
        from integrations import checkin
        found = checkin.port_of(ip) or {}
        switch, port = found.get('switch'), found.get('port')
    return jsonify({'switch': switch, 'port': port, 'area': port_areas.hint(switch, port)})
