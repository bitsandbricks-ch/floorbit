"""Incident board and the seat QR helpdesk (issue #27). Rules live in floorbit/incidents.py.

- ``GET /api/incidents``: the board, for accounts with ``incidents.work`` in their role or a team.
- ``POST /api/incidents``, ``PATCH /api/incidents/<id>``: file and work incidents.
- ``GET /api/incidents/markers``: open incidents per seat and switch, for the floor plan.
- ``GET /api/helpdesk/qr``: the signed help link and QR code of every seat (``incidents.assign``).
- ``GET``/``POST /help/<seat>?k=<signature>``: the attendee's page. No account, nothing personal,
  rate limited; only links printed from the QR sheet work.
"""
import threading
import time

import segno
from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for

from auth import roles, teams
from integrations import events

from .. import audit, incidents, runbooks, spa
from ..store import load_data

bp = Blueprint('incidents', __name__)

# Help page reports per client IP: a printed QR code is no reason to let anyone flood the board.
RATE_LIMIT = 5
RATE_WINDOW = 600
_reports = {}
_reports_lock = threading.Lock()


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def current_user():
    # Imported late: auth imports floorbit (for the SPA shell) while it is still loading.
    from auth import current_user as signed_in
    return signed_in()


def _board_user():
    user = current_user()
    if not user:
        abort(401)
    if not incidents.can_see_board(user):
        abort(403, description='Needs the "work incidents" permission, in your role or a team.')
    return user


def _view(user, incident, match=None, books=None):
    book = runbooks.for_incident(incident, runbooks.all_runbooks() if books is None else books)
    return {**incident, 'can_work': incidents.can_work(user, incident),
            'can_assign': incidents.can_assign(user, incident.get('team')),
            'match': (match or {}).get(incident.get('seat') or ''),
            'runbook': {'id': book['id'], 'title': book['title']} if book else None}


def _changed(incident, action):
    events.publish('incident.changed', {'id': incident['id'], 'status': incident['status'], 'action': action})
    return incident, action


@bp.app_context_processor
def board_link():
    # Templates show the Incidents link and the floor plan markers only to those who can see the board.
    return {'incidents_board': incidents.can_see_board(current_user())}


# ── Pages ──────────────────────────────────────────────────────────────────────
@bp.route('/incidents')
def incidents_page():
    _board_user()
    return spa.render('Incidents')


@bp.route('/incidents/qr')
def qr_page():
    return spa.render('Helpdesk QR codes')


# ── The board ──────────────────────────────────────────────────────────────────
@bp.route('/api/incidents', methods=['GET'])
def list_incidents():
    from ..tournament import match_seats
    user = _board_user()
    all_teams = teams.all_teams()
    match = match_seats()
    books = runbooks.all_runbooks()
    # Match seats (issue #31) on top of each column; the board keeps the newest-first order otherwise.
    items = sorted(incidents.list_all(), key=lambda i: (i['status'] == 'fixed', not match.get(i.get('seat') or '')))
    return jsonify({
        'incidents': [_view(user, i, match, books) for i in items],
        'teams': [{'id': t['id'], 'name': t['name'], 'depth': t['depth']} for t in teams.tree()],
        'workable_teams': sorted(incidents.workable_teams(user)),
        'assign_teams': sorted(t for t in all_teams if incidents.can_assign(user, t)),
        'can_assign_any': roles.can(user, 'incidents.assign'),
        'problems': list(incidents.PROBLEMS),
    })


@bp.route('/api/incidents/people', methods=['GET'])
def people():
    """Who can be given incidents, per team (names only)."""
    _board_user()
    users = current_app.extensions['auth'].users.list()
    out = {}
    for team_id in teams.all_teams():
        out[team_id] = [{'username': u['username'], 'display_name': u['display_name']}
                        for u in users if incidents.can_work(u, {'team': team_id})]
    out[''] = [{'username': u['username'], 'display_name': u['display_name']}
               for u in users if incidents.can_work(u, {'team': None})]
    return jsonify(out)


@bp.route('/api/incidents/markers', methods=['GET'])
def markers():
    _board_user()
    seats, switches = {}, {}
    for i in incidents.list_all():
        if i['status'] == 'fixed':
            continue
        if i.get('seat'):
            seats[i['seat']] = seats.get(i['seat'], 0) + 1
        elif i.get('switch_id'):
            switches[i['switch_id']] = switches.get(i['switch_id'], 0) + 1
    return jsonify({'seats': seats, 'switches': switches})


@bp.route('/api/incidents', methods=['POST'])
def add_incident():
    user = _board_user()
    try:
        incident = incidents.create(user, request.get_json(silent=True) or {})
    except incidents.IncidentError as exc:
        return _error(exc)
    _changed(incident, 'created')
    return jsonify(_view(user, incident)), 201


@bp.route('/api/incidents/<incident_id>', methods=['PATCH'])
def change_incident(incident_id):
    user = _board_user()
    try:
        incident = incidents.update(user, incident_id, request.get_json(silent=True) or {})
    except incidents.IncidentError as exc:
        return _error(exc)
    _changed(incident, 'changed')
    return jsonify(_view(user, incident))


# ── QR sheet ───────────────────────────────────────────────────────────────────
def _help_url(seat):
    base = (current_app.extensions['auth'].public_url() or '').rstrip('/')
    path = url_for('incidents.help_page', seat=seat, k=incidents.signature(seat))
    return base + path if base else url_for('incidents.help_page', seat=seat, k=incidents.signature(seat),
                                             _external=True)


def _seat_key(seat):
    head, _, tail = seat.rpartition('-')
    return (head, int(tail)) if tail.isdigit() else (seat, 0)


@bp.route('/api/helpdesk/qr', methods=['GET'])
def qr_codes():
    seats = sorted(incidents.seat_numbers(), key=_seat_key)
    out = []
    for seat in seats:
        url = _help_url(seat)
        out.append({'seat': seat, 'url': url, 'image': segno.make(url, error='m').svg_data_uri(scale=4, border=2)})
    return jsonify({'seats': out})


# ── The attendee's page ────────────────────────────────────────────────────────
TEXTS = {
    'en': {'title': 'Help at seat {seat}', 'intro': 'Something not working at your seat? Tap what is wrong and '
           'the network team will come to you. We don\'t need your name.',
           'no-internet': 'No internet', 'slow': 'Slow or dropping connection', 'power': 'No power',
           'other': 'Something else, please come by',
           'thanks': 'Thanks, we know. Someone from the team will come to seat {seat}.',
           'again': 'We already have this one for seat {seat} and noted that you asked again.',
           'invalid': 'This help link is not valid. Please use the QR code on your seat, or ask at the info desk.',
           'busy': 'Too many reports from here. Please wait a few minutes or ask at the info desk.',
           'speed_title': 'Test your connection',
           'speed_intro': 'Measures the connection from your seat to our server in the hall, not the internet. '
           'It takes about 20 seconds: pause other downloads first.',
           'speed_run': 'Start the test', 'speed_again': 'Test again', 'speed_running': 'Testing…',
           'speed_down': 'Download', 'speed_up': 'Upload', 'speed_ping': 'Latency',
           'speed_saved': 'Saved for seat {seat}. The team sees it with your report.',
           'speed_failed': 'The test did not finish: {error}'},
    'de': {'title': 'Hilfe an Platz {seat}', 'intro': 'Funktioniert an deinem Platz etwas nicht? Tippe an, was '
           'nicht geht, und das Netzwerk-Team kommt zu dir. Deinen Namen brauchen wir nicht.',
           'no-internet': 'Kein Internet', 'slow': 'Langsame oder abbrechende Verbindung', 'power': 'Kein Strom',
           'other': 'Etwas anderes, bitte vorbeikommen',
           'thanks': 'Danke, wir wissen Bescheid. Jemand vom Team kommt zu Platz {seat}.',
           'again': 'Das haben wir für Platz {seat} schon und vermerkt, dass du nochmals gefragt hast.',
           'invalid': 'Dieser Hilfe-Link ist ungültig. Nutze bitte den QR-Code an deinem Platz oder frag am Infodesk.',
           'busy': 'Zu viele Meldungen von hier. Warte bitte ein paar Minuten oder frag am Infodesk.',
           'speed_title': 'Verbindung testen',
           'speed_intro': 'Misst die Verbindung von deinem Platz zu unserem Server in der Halle, nicht das Internet. '
           'Das dauert etwa 20 Sekunden: halte andere Downloads vorher an.',
           'speed_run': 'Test starten', 'speed_again': 'Nochmals testen', 'speed_running': 'Teste…',
           'speed_down': 'Download', 'speed_up': 'Upload', 'speed_ping': 'Latenz',
           'speed_saved': 'Für Platz {seat} gespeichert. Das Team sieht es bei deiner Meldung.',
           'speed_failed': 'Der Test wurde nicht fertig: {error}'},
}


def _texts():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    return lang, TEXTS[lang]


def _rate_limited():
    ip = request.remote_addr or '?'
    now = time.time()
    with _reports_lock:
        recent = [t for t in _reports.get(ip, []) if now - t < RATE_WINDOW]
        if len(recent) >= RATE_LIMIT:
            _reports[ip] = recent
            return True
        _reports[ip] = [*recent, now]
        if len(_reports) > 10000:   # forget idle clients so the dict can't grow without bound
            for key in [k for k, v in _reports.items() if not v or now - v[-1] > RATE_WINDOW]:
                _reports.pop(key, None)
    return False


@bp.route('/help/<seat>', methods=['GET', 'POST'])
def help_page(seat):
    lang, text = _texts()
    seat = seat.strip().upper()
    valid = incidents.signed(seat, request.args.get('k')) and seat in incidents.seat_numbers(load_data())
    if not valid:
        return render_template('help.html', lang=lang, t=text, seat=seat, state='invalid'), 404
    if request.method == 'GET':
        return render_template('help.html', lang=lang, t=text, seat=seat, state='ask',
                               problems=list(incidents.PROBLEMS), k=request.args.get('k'))
    problem = request.form.get('problem')
    if problem not in incidents.PROBLEMS:
        return render_template('help.html', lang=lang, t=text, seat=seat, state='ask',
                               problems=list(incidents.PROBLEMS), k=request.args.get('k')), 400
    if _rate_limited():
        return render_template('help.html', lang=lang, t=text, seat=seat, state='busy'), 429
    incident, new = incidents.report_from_seat(seat, problem, incidents.seat_snapshot(seat))
    _changed(incident, 'reported')
    audit.record('incidents', 'Reported from seat' if new else 'Reported again from seat', target=seat,
                 fields=[problem])
    return render_template('help.html', lang=lang, t=text, seat=seat, state='thanks' if new else 'again',
                           k=request.args.get('k'))


help_page._auth_public = True   # what auth.public_endpoint sets; open to attendees without an account
