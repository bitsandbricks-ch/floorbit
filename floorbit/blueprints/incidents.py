"""Incident board and the seat QR helpdesk (issue #27). Rules live in floorbit/incidents.py.

- ``GET /api/incidents``: the board, for accounts with ``incidents.work`` in their role or a team.
- ``POST /api/incidents``, ``PATCH /api/incidents/<id>``: file and work incidents.
- ``GET /api/incidents.csv?tz=<minutes>``: the board as a spreadsheet for the debrief after the event
  (issue #418). Same people as the board; never attendee data. The download goes to the audit log.
- ``GET /api/incidents/markers``: open incidents per seat and switch, for the floor plan.
- ``GET /api/helpdesk/qr``: the signed help link and QR code of every seat (``incidents.assign``).
- ``GET``/``POST /help/<seat>?k=<signature>``: the attendee's page. No account, nothing personal,
  rate limited; only links printed from the QR sheet work.
"""
import csv
import functools
import io
import re
import threading
import time

import segno
from flask import Blueprint, Response, abort, current_app, jsonify, request, url_for

from auth import roles, teams
from integrations import checkin, events

from .. import audit, dispatch, incidents, runbooks, seat_notes, spa, speedtest
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


def _stand_in():
    # Sign-in switched off: everyone may do everything, as elsewhere. The board still needs a name
    # to file, take and sign jobs with, so it is one shared crew account.
    from auth.users import public
    return public({'username': 'crew', 'display_name': 'Crew', 'role': 'admin'})


def _board_user():
    user = current_user()
    if not user and not current_app.extensions['auth'].enabled:
        return _stand_in()
    if not user:
        abort(401)
    if not incidents.can_see_board(user):
        abort(403, description='Needs the "work incidents" permission, in your role or a team.')
    return user


def _view(user, incident, match=None, books=None, notes=None, outages=None):
    book = runbooks.for_incident(incident, runbooks.all_runbooks() if books is None else books)
    seat = incident.get('seat') or ''
    # The seat's crew note (issue #204). Everyone on the board works incidents, which is what notes need.
    note = (seat_notes.all_notes() if notes is None else notes).get(seat) if seat else None
    return {**incident, 'can_work': incidents.can_work(user, incident),
            'can_assign': incidents.can_assign(user, incident.get('team')),
            'match': (match or {}).get(seat),
            'runbook': ({k: book.get(k) for k in ('id', 'title', 'starter')} if book else None),
            'seat_note': {k: note.get(k) for k in ('text', 'by', 'at')} if note else None,
            # The seat's switch is down right now (issue #386): part of an outage, not a cable.
            'outage': (outages or {}).get(seat) if incident.get('status') != 'fixed' else None,
            'back_up': (outages or {}).get(('back', incident.get('id'))) if incident.get('status') != 'fixed' else None}


def _outages(items):
    """{seat: {switch, since}} for open incidents whose seat's switch is down now, and
    {('back', incident id): {switch, since}} for ones whose switch came back after they were filed."""
    from .. import seat_view
    statuses = seat_view.monitor_statuses()
    if not statuses:
        return {}
    data = load_data()
    out = {}
    for seat in {i.get('seat') for i in items if i.get('seat') and i['status'] != 'fixed'}:
        found = seat_view.outage_of(seat, data, statuses)
        if found:
            out[seat] = {'switch': found[0], 'since': found[1]}
    # Reported while its switch was down, and the switch is back since (issue #390): maybe fixed already.
    for i in items:
        if i.get('seat') and i['status'] != 'fixed' and i.get('seat') not in out:
            back = seat_view.back_up(i['seat'], i.get('created_at') or 0, data, statuses)
            if back:
                out[('back', i['id'])] = {'switch': back[0], 'since': back[1]}
    return out


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
    notes = seat_notes.all_notes()
    # Match seats (issue #31) on top of each column; the board keeps the newest-first order otherwise.
    items = sorted(incidents.list_all(), key=lambda i: (i['status'] == 'fixed', not match.get(i.get('seat') or '')))
    outages = _outages(items)
    return jsonify({
        'incidents': [_view(user, i, match, books, notes, outages) for i in items],
        'teams': [{'id': t['id'], 'name': t['name'], 'depth': t['depth']} for t in teams.tree()],
        'workable_teams': sorted(incidents.workable_teams(user)),
        'assign_teams': sorted(t for t in all_teams if incidents.can_assign(user, t)),
        'can_assign_any': roles.can(user, 'incidents.assign'),
        'problems': list(incidents.PROBLEMS),
    })


CSV_COLUMNS = ('id', 'created', 'where', 'title', 'team', 'status', 'source', 'reports', 'reported_by',
               'assignee', 'picked_up', 'fixed', 'minutes_to_fix', 'notes')


def _cell(value):
    # A cell starting with = + - @ runs as a formula in Excel or LibreOffice: titles are free text.
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def csv_rows(items, team_names, tz=0):
    """The board as rows for a spreadsheet. No snapshot (nicks, IPs) and no note texts: notes can
    name people, so only their count goes in."""
    def when(at):
        return time.strftime('%Y-%m-%d %H:%M', time.gmtime(at - tz * 60)) if at else ''
    rows = [CSV_COLUMNS]
    for i in sorted(items, key=lambda i: i.get('created_at') or 0):
        where = f"seat {i['seat']}" if i.get('seat') else i.get('switch_name') or i.get('circuit_name') or ''
        fixed = i.get('fixed_at') if i.get('status') == 'fixed' else None
        took = round((fixed - i['created_at']) / 60) if fixed and i.get('created_at') else ''
        rows.append((i['id'], when(i.get('created_at')), where, i.get('title'), team_names.get(i.get('team'), ''),
                     i.get('status'), i.get('source'), i.get('reports') or 1, i.get('reported_by') or '',
                     i.get('assignee') or '', when(i.get('picked_up_at')), when(fixed), took,
                     len(i.get('notes') or [])))
    return [[_cell(v) for v in row] for row in rows]


@bp.route('/api/incidents.csv', methods=['GET'])
def incidents_csv():
    user = _board_user()
    try:
        tz = max(-14 * 60, min(14 * 60, int(request.args.get('tz') or 0)))
    except ValueError:
        tz = 0
    names = {t['id']: t['name'] for t in teams.tree()}
    out = io.StringIO()
    csv.writer(out).writerows(csv_rows(incidents.list_all(), names, tz))
    audit.record('incidents', 'Downloaded the incident list', user=user['username'])
    stamp = time.strftime('%Y-%m-%d', time.gmtime(time.time() - tz * 60))
    # A BOM so Excel reads the umlauts as UTF-8.
    return Response('\ufeff' + out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="incidents-{stamp}.csv"'})


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
    incident = dispatch.send_new(incident)
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
def _card_base():
    """Where the seat cards' QR codes point: the QR_URL setting, else the public URL. Attendees often
    reach Floorbit under another name than the crew (an event DNS name, plain http)."""
    from integrations import config
    raw = str(config.get('QR_URL', '') or '').strip()
    if raw and not re.match(r'^https?://', raw, re.I):
        raw = 'http://' + raw
    return (raw or current_app.extensions['auth'].public_url() or '').rstrip('/')


def _card_url(endpoint, **values):
    base = _card_base()
    return base + url_for(endpoint, **values) if base else url_for(endpoint, _external=True, **values)


def _help_url(seat):
    return _card_url('incidents.help_page', seat=seat, k=incidents.signature(seat))


@functools.lru_cache(maxsize=10000)
def _qr_image(url):
    # segno tries all eight masks for the best scan, about 4 ms a code: 15 s for a 4000-seat sheet.
    # A seat's link only changes with the secret key or the address, so each code is made once.
    return segno.make(url, error='m').svg_data_uri(scale=4, border=2)


def _seat_key(seat):
    head, _, tail = seat.rpartition('-')
    return (head, int(tail)) if tail.isdigit() else (seat, 0)


@bp.route('/api/helpdesk/qr', methods=['GET'])
def qr_codes():
    from integrations import checkin, config
    seats = sorted(incidents.seat_numbers(), key=_seat_key)
    # The card on each seat also says how to check in from the PC (no camera there): the short
    # address and the seat's PIN (integrations/checkin.py).
    checkin_on = config.get_bool('CHECKIN_ENABLED', False)
    pins = checkin.ensure_pins(seats) if checkin_on else {}
    out = []
    for seat in seats:
        url = _help_url(seat)
        row = {'seat': seat, 'url': url, 'image': _qr_image(url)}
        if checkin_on:
            row['pin'] = pins.get(seat)
        out.append(row)
    return jsonify({'seats': out, 'checkin': {
        'address': checkin.short_address() or None,
        'url': _card_url('pages.checkin_page'),
    } if checkin_on else None})


# ── The attendee's page ────────────────────────────────────────────────────────
# ``/help/<seat>?k=<signature>`` is React (frontend/src/pages/public/SeatHelp.tsx). It asks and
# reports through ``/api/helpdesk/seats/<seat>?k=`` with the same signed link, and needs no account.


def _rate_limited(key=None):
    """Too many reports from this client (an IP, or ``discord:<user id>`` for the bot, issue #424)."""
    # Behind a trusted proxy every attendee shares the proxy's address: count the real client instead.
    ip = key or checkin.client_ip() or '?'
    now = time.time()
    with _reports_lock:
        recent = [t for t in _reports.get(ip, []) if 0 <= now - t < RATE_WINDOW]
        if len(recent) >= RATE_LIMIT:
            _reports[ip] = recent
            return True
        _reports[ip] = [*recent, now]
        if len(_reports) > 10000:   # forget idle clients so the dict can't grow without bound
            for key in [k for k, v in _reports.items() if not v or not 0 <= now - v[-1] <= RATE_WINDOW]:
                _reports.pop(key, None)
    return False


def _signed_seat(seat):
    """The seat, when the link is signed for it and it is on the floor plan; else None."""
    seat = seat.strip().upper()
    ok = incidents.signed(seat, request.args.get('k')) and seat in incidents.seat_numbers(load_data())
    return seat if ok else None


def _invalid():
    return jsonify({'error': 'This help link is not valid.', 'code': 'invalid'}), 404


def _busy():
    return jsonify({'error': 'Too many reports from here. Please wait a few minutes.', 'code': 'busy'}), 429


@bp.route('/help/<seat>')
def help_page(seat):
    """The page is React; 404 for a link that isn't signed for a seat on the plan."""
    html, status = spa.render('Help')
    return html, status if _signed_seat(seat) else 404


@bp.route('/api/helpdesk/seats/<seat>', methods=['GET'])
def help_state(seat):
    """What the seat's help page shows: a known outage (minutes), the network back up since a
    report (minutes), this seat's open report and how many are ahead of it."""
    seat = _signed_seat(seat)
    if not seat:
        return _invalid()
    from .. import seat_view
    from .status_page import page_on
    # A known outage at this seat (issue #384): say so before people report it one by one.
    since = seat_view.outage_since(seat)
    outage = max(1, round((time.time() - since) / 60)) if since else None
    # The switch came back after they reported (issue #392): ask them to check before a tech walks over.
    filed = None if outage else incidents.seat_open_since(seat)
    back = seat_view.back_up(seat, filed) if filed else None
    report = incidents.seat_report_state(seat)
    lim = speedtest.limits()
    return jsonify({
        'seat': seat, 'problems': list(incidents.PROBLEMS), 'outage': outage,
        # Point at the public status page for updates, when there is one (issue #388).
        'status_url': url_for('status_page.status_public') if outage and page_on() else None,
        'back_up': max(1, round((time.time() - back[1]) / 60)) if back else None,
        'report': report, 'ahead': incidents.seat_queue_ahead(seat) if report == 'open' else 0,
        # What one speed test may move, so the page stops in time; null while speed tests are off.
        'speedtest': {'test_mb': lim['test_mb']} if lim['on'] else None,
    })


@bp.route('/api/helpdesk/seats/<seat>', methods=['POST'])
def help_report(seat):
    """``{"problem": "slow"}`` reports a problem (``state`` ``thanks``, or ``again`` when the seat
    already has it); ``{"works": true}`` says it works again (``ok``)."""
    seat = _signed_seat(seat)
    if not seat:
        return _invalid()
    body = request.get_json(silent=True) or {}
    if body.get('works'):
        # Rate limited like reports: it only tags the incidents, but it still writes to the board.
        if _rate_limited():
            return _busy()
        marked = incidents.seat_says_ok(seat)
        for incident in marked:
            _changed(incident, 'seat-ok')
        if marked:
            audit.record('incidents', 'Seat says it works again', target=seat)
        return jsonify({'state': 'ok'})
    problem = body.get('problem')
    if problem not in incidents.PROBLEMS:
        return jsonify({'error': 'Pick one of the problems on the page.', 'code': 'problem'}), 400
    if _rate_limited():
        return _busy()
    incident, new = incidents.report_from_seat(seat, problem, incidents.seat_snapshot(seat))
    _changed(incident, 'reported')
    if new:
        dispatch.send_new(incident)
    audit.record('incidents', 'Reported from seat' if new else 'Reported again from seat', target=seat,
                 fields=[problem])
    return jsonify({'state': 'thanks' if new else 'again'})


for _public in (help_page, help_state, help_report):
    _public._auth_public = True   # what auth.public_endpoint sets; open to attendees without an account
