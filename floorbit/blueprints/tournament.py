"""Tournament awareness (issue #31): match zones and QoS hints. Rules in floorbit/tournament.py.

- ``GET /tournament``: the page (React).
- ``GET /api/tournament``: the match zones, every match seat, and each hall's plan with them marked.
- ``POST /api/tournament/zones``, ``PATCH``/``DELETE /api/tournament/zones/<id>``: change zones
  (``floorplan.edit``).
- ``GET /api/tournament/seats``: seat -> zone, for the floor plan editor.
- ``GET /api/tournament/qos``: the switch ports behind the match seats; asks the monitoring source.
"""
from flask import Blueprint, jsonify, request

from integrations import events

from .. import halls, spa, tournament
from ..store import load_data
from .screen import plan

bp = Blueprint('tournament', __name__)


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _changed():
    events.publish('tournament.changed', {})


@bp.route('/tournament')
def tournament_page():
    return spa.render('Tournament seats')


@bp.route('/api/tournament', methods=['GET'])
def overview():
    data = load_data()
    seats = tournament.match_seats(data)
    plans = []
    for hall in halls.halls(data):
        drawing, _ = plan(data, online=set(seats), hall_id=hall['id'])
        if drawing:
            plans.append({'hall': hall['id'], 'name': hall['name'], 'drawing': drawing,
                          'match': sum(1 for s in drawing['shapes'] for c in s['cells'] if c['on'])})
    return jsonify({'zones': tournament.zones(data), 'seats': seats, 'plans': plans})


@bp.route('/api/tournament/seats', methods=['GET'])
def seats():
    return jsonify(tournament.match_seats())


@bp.route('/api/tournament/zones', methods=['POST'])
def add_zone():
    try:
        zone = tournament.create(request.get_json(silent=True) or {})
    except tournament.TournamentError as exc:
        return _error(exc)
    _changed()
    return jsonify(zone), 201


@bp.route('/api/tournament/zones/<zone_id>', methods=['PATCH'])
def change_zone(zone_id):
    try:
        zone = tournament.update(zone_id, request.get_json(silent=True) or {})
    except tournament.TournamentError as exc:
        return _error(exc)
    _changed()
    return jsonify(zone)


@bp.route('/api/tournament/zones/<zone_id>', methods=['DELETE'])
def delete_zone(zone_id):
    try:
        zone = tournament.delete(zone_id)
    except tournament.TournamentError as exc:
        return _error(exc)
    _changed()
    return jsonify(zone)


@bp.route('/api/tournament/qos', methods=['GET'])
def qos():
    return jsonify(tournament.qos_hints())
