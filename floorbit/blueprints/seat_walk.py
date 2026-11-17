"""The crew's walk-through check-in (floorbit/seat_walk.py, docs/seat-walk.md).

- ``GET /seat-walk``: the page (React).
- ``GET /api/seat-walk?block=&order=``: the block's seats in walking order with the port each has
  in this event, this laptop's IP and which ways of looking it up are on.
- ``POST /api/seat-walk/locate``: ``{"seat", "previous": {"switch", "port"}, "mac"}``: find the
  port this laptop is plugged into now and keep it for the seat. Tries for about 20 seconds;
  ``retry`` says whether trying again is worth it.
- ``DELETE /api/seat-walk/<seat>``: forget the seat's port (a wrong one).

Reading needs ``seats.view`` (it names the laptop's MAC), changing ``seats.edit`` (auth/roles.py).
"""
from flask import Blueprint, current_app, g, jsonify, request

from integrations import checkin

from .. import seat_walk, sources, spa, tenancy
from ..store import load_data

bp = Blueprint('seat_walk', __name__)


def _registry():
    return current_app.extensions.get('floorbit_plugins')


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username') or 'crew'


@bp.route('/seat-walk')
def page():
    return spa.render('Seat walk-through')


@bp.route('/api/seat-walk', methods=['GET'])
def overview():
    ip = checkin.client_ip()
    body = {'ip': ip, 'ip_allowed': checkin.ip_allowed(ip),
            'switch_lookup': seat_walk._ssh(_registry())[0] is not None,
            'monitoring': sources.monitoring().enabled(),
            'event': {k: tenancy.current().get(k) for k in ('id', 'name', 'status')},
            'keep_hours': seat_walk.KEEP_AFTER_END // 3600}
    block = request.args.get('block')
    if block:
        try:
            body.update(seat_walk.seats(block, request.args.get('order') or 'rows'))
        except seat_walk.WalkError as exc:
            return jsonify({'error': str(exc)}), exc.status
    return jsonify(body)


def _port(value):
    if not isinstance(value, dict) or not value.get('switch') or not value.get('port'):
        return None
    return {'switch': str(value['switch'])[:80], 'port': str(value['port'])[:48]}


@bp.route('/api/seat-walk/locate', methods=['POST'])
def locate():
    body = request.get_json(silent=True) or {}
    seat = str(body.get('seat') or '').strip().upper()[:16]
    if not seat or seat not in {s.upper() for s in checkin.known_seats(load_data)}:
        return jsonify({'error': 'That seat is not on the floor plan.'}), 400
    ip = checkin.client_ip()
    if not checkin.ip_allowed(ip):
        return jsonify({'error': f'This laptop has {ip}, which is not in the seat networks. '
                                 'Turn off Wi-Fi and plug the cable in.', 'ip': ip}), 409
    registry = _registry()
    if seat_walk._ssh(registry)[0] is None and not sources.monitoring().enabled():
        return jsonify({'error': 'Nothing can look up switch ports: turn on SSH port actions, telemetry '
                                 'or LibreNMS, or connect a local agent.'}), 409
    previous = _port(body.get('previous'))
    # The MAC the last seat found, while the laptop still has the same IP: saves the ARP lookup.
    mac = seat_walk._mac(body.get('mac')) if body.get('mac') and body.get('mac_ip') == ip else None
    result = seat_walk.locate(ip, registry, g.get('audit_user') or _who(), previous,
                              seat_walk.likely_switches(seat, previous), mac=mac)
    out = {'seat': seat, 'ip': ip, 'mac': result['mac'], 'how': result['how'], 'ms': result['ms'],
           'tries': result['tries'], 'steps': result['steps'], 'stale': result['stale'], 'found': result['found']}
    if not result['found']:
        return jsonify({**out, 'ok': False, 'retry': True})
    saved = seat_walk.save(seat, result['found'], _who())
    return jsonify({**out, 'ok': True, 'retry': False, **saved})


@bp.route('/api/seat-walk/<seat>', methods=['DELETE'])
def forget(seat):
    if not checkin.forget_port(seat.strip().upper()):
        return jsonify({'error': 'That seat has no learned port'}), 404
    return jsonify({'ok': True})
