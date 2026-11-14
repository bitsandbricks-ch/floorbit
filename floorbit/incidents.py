"""Incidents: problems during the event, tied to a seat or a switch. See docs/incidents.md.

Stored in data.json under ``incidents``. Who may see and change what follows the permissions in
auth/roles.py, scoped by team (auth/teams.py):

- the board needs ``incidents.work`` somewhere: in the account's own role or a team role;
- working an incident (take it, mark it fixed, add a note) needs ``incidents.work`` in its team,
  through a membership of that team or one above it; incidents without a team need it globally;
- moving an incident to another team, or giving it to someone else, needs ``incidents.assign``
  (globally, or as a team role in both teams).

Attendees report problems from a QR code on their seat (``/help/<seat>``): the link is signed with
the app's secret key, so only printed codes work, and the report asks for nothing personal.
"""
import hashlib
import hmac
import threading
import time
import uuid

from flask import current_app

from auth import roles, teams

from .store import load_data, save_data

KEY = 'incidents'
STATUSES = ('open', 'assigned', 'fixed')
# What an attendee can pick on the help page, and the team it goes to first (if that team exists).
# Admins rename or remove teams; then the report lands without a team for anyone with incidents.assign.
PROBLEMS = {
    'no-internet': 'access',
    'slow': 'access',
    'power': 'electrics',
    'other': 'operations',
}
MAX_TITLE = 120
MAX_NOTE = 2000
MAX_KEPT = 2000           # oldest fixed incidents are dropped beyond this
SIGNATURE_LENGTH = 16

_lock = threading.Lock()


class IncidentError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ── Seats ──────────────────────────────────────────────────────────────────────
def seat_numbers(data=None):
    """Every seat number on the floor plan, numbered like the editor (block name + 1..n)."""
    data = data if data is not None else load_data()
    out = set()
    for block in data.get('seat_blocks') or []:
        prefix = f"{str(block.get('name')).upper()}-" if block.get('name') else ''
        total = int(block.get('cols') or 0) * int(block.get('rows') or 0)
        out.update(f'{prefix}{n}' for n in range(1, total + 1))
    out.update(str(s['number']) for s in data.get('seats') or [] if s.get('number'))
    return out


def signature(seat):
    """The part of a seat's help link that proves it was printed here."""
    secret = current_app.config['SECRET_KEY']
    secret = secret.encode() if isinstance(secret, str) else secret
    return hmac.new(secret, f'helpdesk:{seat}'.encode(), hashlib.sha256).hexdigest()[:SIGNATURE_LENGTH]


def signed(seat, given):
    return bool(given) and hmac.compare_digest(signature(seat), str(given))


# ── Who may do what ────────────────────────────────────────────────────────────
def _team_can(user, team_id, permission):
    """Through a membership of this team or one above it (not just the account's own role)."""
    return team_id in teams.teams_of(user) and permission in teams.team_permissions(user, team_id)


def can_see_board(user):
    if not user:
        return False
    if roles.can(user, 'incidents.work') or roles.can(user, 'incidents.assign'):
        return True
    return any('incidents.work' in teams.team_permissions(user, t) for t in teams.teams_of(user))


def can_work(user, incident):
    if roles.can(user, 'incidents.assign'):
        return True
    team = incident.get('team')
    if not team:
        return roles.can(user, 'incidents.work')
    return _team_can(user, team, 'incidents.work')


def can_assign(user, team_id):
    """May route incidents into (and out of) this team, or give them to anyone in it."""
    if roles.can(user, 'incidents.assign'):
        return True
    return bool(team_id) and _team_can(user, team_id, 'incidents.assign')


def workable_teams(user):
    """Teams this account may file or take incidents for."""
    all_teams = teams.all_teams()
    if roles.can(user, 'incidents.assign'):
        return set(all_teams)
    return {t for t in teams.teams_of(user) if t in all_teams and _team_can(user, t, 'incidents.work')}


# ── Storage ────────────────────────────────────────────────────────────────────
def _all(data):
    return [i for i in data.get(KEY) or [] if isinstance(i, dict)]


def _save(data, items):
    fixed = [i for i in items if i['status'] == 'fixed']
    if len(items) > MAX_KEPT and fixed:
        drop = {i['id'] for i in sorted(fixed, key=lambda i: i['updated_at'])[:len(items) - MAX_KEPT]}
        items = [i for i in items if i['id'] not in drop]
    data[KEY] = items
    save_data(data)


def list_all():
    return sorted(_all(load_data()), key=lambda i: (i['status'] == 'fixed', -i['created_at']))


def get(incident_id):
    return next((i for i in _all(load_data()) if i['id'] == incident_id), None)


def _clean_text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _where(data, seat, switch_id):
    if bool(seat) == bool(switch_id):
        raise IncidentError('An incident is about one seat or one switch.')
    if seat:
        seat = str(seat).strip().upper()
        if seat not in seat_numbers(data):
            raise IncidentError(f'There is no seat {seat} on the floor plan.')
        return {'seat': seat, 'switch_id': None}
    switch = next((d for d in data.get('inventory') or [] if d.get('id') == switch_id), None)
    if not switch:
        raise IncidentError('There is no such switch.')
    return {'seat': None, 'switch_id': switch_id, 'switch_name': switch.get('name')}


def _check_team(team_id):
    if team_id and team_id not in teams.all_teams():
        raise IncidentError(f'No team called {team_id}.')
    return team_id or None


def _check_assignee(username, team_id):
    if not username:
        return None
    user = current_app.extensions['auth'].users.get(username)
    if not user:
        raise IncidentError(f'No user called {username}.')
    if not can_work(user, {'team': team_id}):
        raise IncidentError(f"{user['username']} can't work incidents for this team.")
    return user['username']


def create(user, body, snapshot=None, source='board'):
    """A new incident. ``user`` is None for an attendee's report from the help page."""
    with _lock:
        data = load_data()
        where = _where(data, body.get('seat'), body.get('switch_id'))
        team = _check_team(body.get('team'))
        if user is not None:
            allowed = (can_assign(user, team) or team in workable_teams(user)) if team \
                else roles.can(user, 'incidents.work') or roles.can(user, 'incidents.assign')
            if not allowed:
                raise IncidentError("You can't file incidents for that team.", 403)
        title = _clean_text(body.get('title'), MAX_TITLE)
        if not title:
            raise IncidentError('Say in a few words what is wrong.')
        now = time.time()
        incident = {
            'id': uuid.uuid4().hex[:12], **where, 'title': title, 'problem': body.get('problem'),
            'team': team, 'status': 'open', 'assignee': None, 'source': source,
            'reported_by': user['username'] if user else None, 'reports': 1,
            'notes': [], 'snapshot': snapshot, 'created_at': now, 'updated_at': now,
        }
        note = _clean_text(body.get('note'), MAX_NOTE)
        if note:
            incident['notes'].append({'by': user['username'] if user else None, 'at': now, 'text': note})
        items = _all(data)
        items.append(incident)
        _save(data, items)
        return incident


def report_from_seat(seat, problem, snapshot):
    """An attendee's report. A second report for an open incident at the same seat just counts up."""
    with _lock:
        data = load_data()
        for incident in _all(data):
            if incident.get('seat') == seat and incident['source'] == 'helpdesk' \
                    and incident['status'] != 'fixed' and incident.get('problem') == problem:
                incident['reports'] = int(incident.get('reports') or 1) + 1
                incident['updated_at'] = time.time()
                if snapshot:
                    incident['snapshot'] = snapshot
                _save(data, _all(data))
                return incident, False
    team = PROBLEMS[problem] if PROBLEMS[problem] in teams.all_teams() else None
    titles = {'no-internet': 'No internet at the seat', 'slow': 'Slow connection', 'power': 'No power at the seat',
              'other': 'Needs help at the seat'}
    return create(None, {'seat': seat, 'title': titles[problem], 'problem': problem, 'team': team},
                  snapshot=snapshot, source='helpdesk'), True


def update(user, incident_id, body):
    with _lock:
        data = load_data()
        items = _all(data)
        incident = next((i for i in items if i['id'] == incident_id), None)
        if not incident:
            raise IncidentError('No such incident.', 404)
        if not can_work(user, incident):
            raise IncidentError("You can't work incidents for this team.", 403)
        now = time.time()
        if 'team' in body and (body['team'] or None) != incident.get('team'):
            team = _check_team(body['team'])
            if not (can_assign(user, incident.get('team')) and can_assign(user, team)):
                raise IncidentError('Moving incidents between teams needs the "assign incidents" permission.', 403)
            incident['team'] = team
            # Whoever had it may not work for the new team: then it waits there unassigned.
            holder = incident['assignee'] and current_app.extensions['auth'].users.get(incident['assignee'])
            if incident['assignee'] and not (holder and can_work(holder, incident)):
                incident['assignee'] = None
                if incident['status'] == 'assigned':
                    incident['status'] = 'open'
        if 'assignee' in body:
            who = (body['assignee'] or '').strip().lower() or None
            if who and who != user['username'].lower() and not can_assign(user, incident.get('team')):
                raise IncidentError('Giving incidents to someone else needs the "assign incidents" permission.', 403)
            incident['assignee'] = _check_assignee(who, incident.get('team'))
            if incident['status'] != 'fixed':
                incident['status'] = 'assigned' if incident['assignee'] else 'open'
        if 'status' in body:
            status = body['status']
            if status not in STATUSES:
                raise IncidentError(f"Status must be one of: {', '.join(STATUSES)}.")
            if status == 'assigned' and not incident['assignee']:
                incident['assignee'] = user['username']
            if status == 'open':
                incident['assignee'] = None
            incident['status'] = status
            incident['fixed_at'] = now if status == 'fixed' else None
        note = _clean_text(body.get('note'), MAX_NOTE)
        if note:
            incident['notes'].append({'by': user['username'], 'at': now, 'text': note})
        title = _clean_text(body.get('title'), MAX_TITLE) if 'title' in body else None
        if title:
            incident['title'] = title
        incident['updated_at'] = now
        _save(data, items)
        return incident


# ── What the network says about a seat, attached to helpdesk reports ───────────
def seat_snapshot(seat):
    """Switch, port and link state for a seat, without personal data (no IP, MAC or nick)."""
    from integrations import seat_sources

    from . import sources
    try:
        mapping = (seat_sources.load() or {}).get(seat) or {}
        ip = mapping.get('ip_address')
        if not ip and mapping.get('mac'):
            ip = sources.monitoring().ip_for_mac(mapping['mac'])
        if not ip:
            return {'known': False, 'reason': 'No IP or MAC known for this seat'}
        found = sources.monitoring().resolve_ip(ip) or {}
    except Exception as exc:  # noqa: BLE001  # a report must never fail because the network lookup did
        print(f'[incidents] snapshot for {seat} failed: {exc}')
        return {'known': False, 'reason': 'The network lookup failed'}
    if not found.get('device_name'):
        return {'known': False, 'reason': 'The IP was not found on any switch port'}
    stats = found.get('stats') or {}
    return {
        'known': True, 'switch': found.get('device_name'), 'port': found.get('port'),
        'link': stats.get('state'), 'speed_bps': stats.get('speed_bps'), 'duplex': stats.get('duplex'),
        'error_rate': stats.get('error_rate'), 'mac_seen': bool(found.get('mac')),
        'stale': bool(found.get('stale')), 'at': time.time(),
    }
