"""Tournament brackets (issue #107). The rules live in floorbit/brackets.py; see docs/tournament.md.

- ``GET /tournament/brackets``: the crew's page (React).
- ``GET /api/tournament/brackets``: every bracket with its matches, seats and the zones they're in.
- ``POST /api/tournament/brackets``: ``{"name", "teams": [...], "zone_id"}``, a new single-elimination bracket.
- ``PATCH`` / ``DELETE /api/tournament/brackets/<id>``: rename it or move it to another zone; remove it.
- ``PATCH /api/tournament/brackets/<id>/matches/<match>``: ``a_score``, ``b_score``, ``status``,
  ``winner`` (``a`` or ``b``), ``seats`` ("A-1..A-5"), ``station``.
- ``POST /api/tournament/brackets/import``: ask the plugins that send brackets again.
- ``GET /bracket``: the public view for big screens (``?screen=1``, ``?id=<bracket>``), no account. Off
  unless Settings > Attendee pages turns it on.
- ``GET /bracket.json``: the same as JSON.

Changing brackets needs ``floorplan.edit``, like the match zones (auth/roles.py).
"""
import time

from flask import Blueprint, current_app, g, jsonify, render_template, request

from integrations import events

from .. import audit, brackets, spa, tournament
from ..store import load_data
from .status_page import _stamp

bp = Blueprint('brackets', __name__)

TEXTS = {
    'en': {'title': 'Brackets', 'off': 'This page is switched off.', 'empty': 'No brackets yet.',
           'round': 'Round {n}', 'final': 'Final', 'semi': 'Semi-finals', 'quarter': 'Quarter-finals',
           'live': 'Live', 'tbd': 'to be decided', 'champion': 'Champion', 'bye': 'bye',
           'updated': 'Updated {time}. This page reloads every 30 seconds.'},
    'de': {'title': 'Turnierbäume', 'off': 'Diese Seite ist ausgeschaltet.', 'empty': 'Noch keine Turnierbäume.',
           'round': 'Runde {n}', 'final': 'Final', 'semi': 'Halbfinals', 'quarter': 'Viertelfinals',
           'live': 'Live', 'tbd': 'offen', 'champion': 'Sieger', 'bye': 'Freilos',
           'updated': 'Stand {time}. Die Seite lädt alle 30 Sekunden neu.'},
}


def page_on():
    return bool(current_app.extensions['floorbit_settings'].get('public.brackets'))


def _registry():
    return current_app.extensions['floorbit_plugins']


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _changed():
    events.publish('brackets.changed', {})


def _error(exc):
    return jsonify({'error': str(exc)}), exc.status


@bp.route('/tournament/brackets')
def brackets_page():
    return spa.render('Brackets')


@bp.route('/api/tournament/brackets', methods=['GET'])
def list_brackets():
    data = load_data()
    seat_zone = tournament.match_seats(data)
    zones = tournament.zones(data)
    out = []
    for b in brackets.all_brackets(data):
        rounds = [[{**m, 'zones': sorted({seat_zone[s] for s in m.get('seats') or [] if s in seat_zone})} for m in rnd]
                  for rnd in b['rounds']]
        out.append({**b, 'rounds': rounds})
    return jsonify({'brackets': out, 'zones': [{'id': z['id'], 'name': z['name']} for z in zones],
                    'sources': [s.name for s in brackets.sources(_registry())], 'public': page_on()})


@bp.route('/api/tournament/brackets', methods=['POST'])
def create_bracket():
    try:
        b = brackets.create(request.get_json(silent=True) or {}, _who())
    except brackets.BracketError as exc:
        return _error(exc)
    audit.record('tournament', 'Added a bracket', g.get('audit_user'), b['name'])
    _changed()
    return jsonify(b), 201


@bp.route('/api/tournament/brackets/import', methods=['POST'])
def import_brackets():
    try:
        count, errors = brackets.import_from(_registry(), _who())
    except brackets.BracketError as exc:
        return _error(exc)
    audit.record('tournament', 'Imported brackets', g.get('audit_user'), f'{count} bracket(s)')
    _changed()
    return jsonify({'count': count, 'errors': errors})


@bp.route('/api/tournament/brackets/<bracket_id>', methods=['PATCH'])
def change_bracket(bracket_id):
    try:
        b = brackets.update(bracket_id, request.get_json(silent=True) or {}, _who())
    except brackets.BracketError as exc:
        return _error(exc)
    audit.record('tournament', 'Changed a bracket', g.get('audit_user'), b['name'])
    _changed()
    return jsonify(b)


@bp.route('/api/tournament/brackets/<bracket_id>', methods=['DELETE'])
def delete_bracket(bracket_id):
    try:
        brackets.delete(bracket_id)
    except brackets.BracketError as exc:
        return _error(exc)
    audit.record('tournament', 'Removed a bracket', g.get('audit_user'), bracket_id)
    _changed()
    return jsonify({'ok': True})


@bp.route('/api/tournament/brackets/<bracket_id>/matches/<match_id>', methods=['PATCH'])
def change_match(bracket_id, match_id):
    try:
        b = brackets.set_match(bracket_id, match_id, request.get_json(silent=True) or {}, _who())
    except brackets.BracketError as exc:
        return _error(exc)
    audit.record('tournament', 'Entered a match result', g.get('audit_user'), f"{b['name']} {match_id}")
    _changed()
    return jsonify(b)


def _public():
    data = load_data()
    zones = {z['id']: z for z in tournament.zones(data)}
    return [brackets.public_view(b, zones) for b in brackets.all_brackets(data)]


@bp.route('/bracket')
def bracket_page():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    text = TEXTS[lang]
    if not page_on():
        return render_template('bracket.html', lang=lang, t=text, off=True), 404
    shown = _public()
    wanted = request.args.get('id')
    current = next((b for b in shown if b['id'] == wanted), shown[0] if shown else None)
    return render_template('bracket.html', lang=lang, t=text, off=False, all=shown, b=current, now=time.time(),
                           stamp=_stamp, screen=request.args.get('screen') == '1')


@bp.route('/bracket.json')
def bracket_json():
    if not page_on():
        return jsonify({'error': 'The bracket view is switched off.'}), 404
    return jsonify({'brackets': _public()})


for _view in (bracket_page, bracket_json):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account
