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
from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, url_for

from auth import roles, teams
from integrations import checkin, events

from .. import audit, dispatch, incidents, runbooks, seat_notes, spa
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
           'speed_failed': 'The test did not finish: {error}',
           'state_open': 'Your report is in. Nobody from the team has taken it yet; someone will come.',
           'state_sent': 'Your report was sent to a tech nearby. They will be on their way shortly.',
           'state_taken': 'Someone from the team has your report and is on the way.',
           'state_fixed': 'Your report was marked fixed. Still not working? Tap it again below.',
           'state_ok': 'You told us it works again. Thanks! Broken again? Tap it below.',
           'ahead_one': 'One report is ahead of yours.', 'ahead_other': '{n} reports are ahead of yours.',
           'outage': 'We know: the network at your seat has been down for {m} min. The team is on it, '
           'no need to report it. Something else? Tap it below.',
           'status_link': 'Updates on the network status page',
           'works': 'It works again', 'works_hint': 'Fixed itself? Tell the team so nobody walks over for nothing.',
           'ok_thanks': 'Thanks, we told the team it works again at seat {seat}.',
           'back_up': 'The network at your seat has been back for {m} min. Does it work again? Then tap '
           '"It works again" below.'},
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
           'speed_failed': 'Der Test wurde nicht fertig: {error}',
           'state_open': 'Deine Meldung ist da. Noch hat sie niemand vom Team übernommen; jemand kommt.',
           'state_sent': 'Deine Meldung ging an jemanden vom Team in der Nähe. Gleich ist jemand unterwegs.',
           'state_taken': 'Jemand vom Team hat deine Meldung und ist unterwegs.',
           'state_fixed': 'Deine Meldung wurde als erledigt markiert. Geht es immer noch nicht? Tippe unten nochmals.',
           'state_ok': 'Du hast gemeldet, dass es wieder geht. Danke! Wieder kaputt? Tippe unten.',
           'ahead_one': 'Vor deiner ist noch eine Meldung.', 'ahead_other': 'Vor deiner sind noch {n} Meldungen.',
           'outage': 'Wir wissen es: Das Netz an deinem Platz ist seit {m} Min. ausgefallen. Das Team ist dran, '
           'du musst es nicht melden. Etwas anderes? Tippe es unten an.',
           'status_link': 'Neuigkeiten auf der Netzwerk-Statusseite',
           'works': 'Es geht wieder',
           'works_hint': 'Hat es sich selbst gelöst? Sag es dem Team, damit niemand umsonst vorbeikommt.',
           'ok_thanks': 'Danke, wir haben dem Team gesagt, dass es an Platz {seat} wieder geht.',
           'back_up': 'Das Netz an deinem Platz ist seit {m} Min. wieder da. Geht es wieder? Dann tippe unten '
           'auf «Es geht wieder».'},
}


def _texts():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    return lang, TEXTS[lang]


def _rate_limited(key=None):
    """Too many reports from this client (an IP, or ``discord:<user id>`` for the bot, issue #424)."""
    # Behind a trusted proxy every attendee shares the proxy's address: count the real client instead.
    ip = key or checkin.client_ip() or '?'
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
        from .. import seat_view
        # A known outage at this seat (issue #384): say so before people report it one by one.
        since = seat_view.outage_since(seat)
        outage = max(1, round((time.time() - since) / 60)) if since else None
        from .status_page import page_on
        # Point at the public status page for updates, when there is one (issue #388).
        status_url = url_for('status_page.status_public') if outage and page_on() else None
        # The switch came back after they reported (issue #392): ask them to check before a tech walks over.
        filed = None if outage else incidents.seat_open_since(seat)
        back = seat_view.back_up(seat, filed) if filed else None
        back_up = max(1, round((time.time() - back[1]) / 60)) if back else None
        return render_template('help.html', lang=lang, t=text, seat=seat, state='ask', outage=outage,
                               status_url=status_url, back_up=back_up,
                               problems=list(incidents.PROBLEMS), k=request.args.get('k'),
                               report=incidents.seat_report_state(seat), ahead=incidents.seat_queue_ahead(seat))
    if request.form.get('works'):
        return _works_again(lang, text, seat)
    problem = request.form.get('problem')
    if problem not in incidents.PROBLEMS:
        return render_template('help.html', lang=lang, t=text, seat=seat, state='ask',
                               problems=list(incidents.PROBLEMS), k=request.args.get('k')), 400
    if _rate_limited():
        return render_template('help.html', lang=lang, t=text, seat=seat, state='busy'), 429
    incident, new = incidents.report_from_seat(seat, problem, incidents.seat_snapshot(seat))
    _changed(incident, 'reported')
    if new:
        dispatch.send_new(incident)
    audit.record('incidents', 'Reported from seat' if new else 'Reported again from seat', target=seat,
                 fields=[problem])
    return render_template('help.html', lang=lang, t=text, seat=seat, state='thanks' if new else 'again',
                           k=request.args.get('k'))


def _works_again(lang, text, seat):
    # Rate limited like reports: it only tags the incidents, but it still writes to the board.
    if _rate_limited():
        return render_template('help.html', lang=lang, t=text, seat=seat, state='busy'), 429
    marked = incidents.seat_says_ok(seat)
    for incident in marked:
        _changed(incident, 'seat-ok')
    if marked:
        audit.record('incidents', 'Seat says it works again', target=seat)
    return render_template('help.html', lang=lang, t=text, seat=seat, state='ok', k=request.args.get('k'))


help_page._auth_public = True   # what auth.public_endpoint sets; open to attendees without an account
