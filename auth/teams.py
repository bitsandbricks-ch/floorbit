"""Teams and sub-teams, and who is in which with what role. See docs/auth.md.

Teams are a tree kept in data.json under ``auth_teams``; memberships sit on each account as
``teams: {team_id: role}``. A membership counts for the team and every team below it, so a lead
of Infra leads Core, Access and Wi-Fi too, and Infra's members see what is routed to its
sub-teams. Team roles only add permissions inside those teams; the account's own role still
decides everything else.
"""
import os
import re
import threading
import uuid

from . import roles

KEY = 'auth_teams'
MAX_TEAMS = 200
MAX_DEPTH = 5
# The teams a new install starts with (Mike, 2026-11-14). Admins rename, move or remove them.
DEFAULTS = (('operations', 'Operations', None), ('infra', 'Infra', None), ('core', 'Core', 'infra'),
            ('access', 'Access', 'infra'), ('wifi', 'Wi-Fi', 'infra'), ('electrics', 'Electrics', None))
NAME_RE = re.compile(r'^[^\x00-\x1f<>]{1,40}$')

_lock = threading.Lock()
_path = None


class TeamError(ValueError):
    pass


def configure(path_getter):
    global _path
    _path = path_getter


def _read():
    path = _path() if _path else None
    if not path or not os.path.exists(path):
        return {}
    from floorbit.store import read_json  # late: floorbit imports auth while it loads
    return read_json(path, {})


def _write(data):
    from floorbit.store import write_json  # in place: data.json is bind-mounted
    write_json(_path(), data)


def _teams(data):
    raw = data.get(KEY)
    if raw is None:   # never set up: the defaults
        return {tid: {'id': tid, 'name': name, 'parent': parent} for tid, name, parent in DEFAULTS}
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


# reads ----------------------------------------------------------------------------------------
def all_teams():
    return _teams(_read())


def ancestors(team_id, teams=None):
    """The team and every team above it, nearest first."""
    teams = teams if teams is not None else all_teams()
    out, seen = [], set()
    while team_id and team_id in teams and team_id not in seen:
        seen.add(team_id)
        out.append(team_id)
        team_id = teams[team_id].get('parent')
    return out


def descendants(team_id, teams=None):
    teams = teams if teams is not None else all_teams()
    out = [team_id]
    for tid, t in teams.items():
        if t.get('parent') == team_id:
            out.extend(descendants(tid, teams))
    return out


def tree():
    """Teams in display order (parents before children) with their depth and members."""
    data = _read()
    teams = _teams(data)
    members = {}
    for u in (data.get('auth_users') or {}).values():
        for tid, role in (u.get('teams') or {}).items():
            members.setdefault(tid, []).append({'username': u['username'], 'role': roles.of({'role': role}),
                                                'role_label': roles.label(roles.of({'role': role}))})
    out = []

    def walk(parent, depth):
        for tid, t in sorted(((k, v) for k, v in teams.items() if v.get('parent') == parent),
                             key=lambda kv: kv[1]['name'].lower()):
            out.append({'id': tid, 'name': t['name'], 'parent': parent, 'depth': depth,
                        'members': sorted(members.get(tid, []), key=lambda m: m['username'].lower())})
            walk(tid, depth + 1)
    walk(None, 0)
    return out


def team_permissions(user, team_id):
    """What this account may do in a team: its own role plus its role in the team or any team above."""
    perms = set(roles.permissions_of(roles.of(user)))
    memberships = (user or {}).get('teams') or {}
    for tid in ancestors(team_id):
        if tid in memberships:
            perms |= roles.permissions_of(roles.of({'role': memberships[tid]}))
    return perms


def teams_of(user):
    """Every team this account belongs to, directly or through a team above it."""
    teams = all_teams()
    out = set()
    for tid in (user or {}).get('teams') or {}:
        if tid in teams:
            out.update(descendants(tid, teams))
    return out


# writes ---------------------------------------------------------------------------------------
def _clean_name(name):
    name = (name or '').strip()
    if not NAME_RE.match(name):
        raise TeamError('A team name is 1 to 40 characters.')
    return name


def _check_parent(teams, team_id, parent):
    if parent is None:
        return
    if parent not in teams:
        raise TeamError(f'No team called {parent}.')
    chain = ancestors(parent, teams)
    if team_id in chain:
        raise TeamError('A team cannot be inside itself.')
    if len(chain) >= MAX_DEPTH:
        raise TeamError(f'Teams go at most {MAX_DEPTH} levels deep.')


def _save(data, teams):
    data[KEY] = teams
    _write(data)


def create(name, parent=None):
    with _lock:
        data = _read()
        teams = _teams(data)
        if len(teams) >= MAX_TEAMS:
            raise TeamError(f'At most {MAX_TEAMS} teams.')
        parent = parent or None
        _check_parent(teams, None, parent)
        tid = uuid.uuid4().hex[:12]
        teams[tid] = {'id': tid, 'name': _clean_name(name), 'parent': parent}
        _save(data, teams)
        return teams[tid]


def update(team_id, name=None, parent=...):
    with _lock:
        data = _read()
        teams = _teams(data)
        team = teams.get(team_id)
        if not team:
            raise TeamError(f'No team called {team_id}.')
        if name is not None:
            team['name'] = _clean_name(name)
        if parent is not ...:
            parent = parent or None
            _check_parent(teams, team_id, parent)
            team['parent'] = parent
        _save(data, teams)
        return team


def delete(team_id):
    """Remove a team without sub-teams; its memberships go with it."""
    with _lock:
        data = _read()
        teams = _teams(data)
        if team_id not in teams:
            raise TeamError(f'No team called {team_id}.')
        if any(t.get('parent') == team_id for t in teams.values()):
            raise TeamError('Move or remove its sub-teams first.')
        del teams[team_id]
        for u in (data.get('auth_users') or {}).values():
            (u.get('teams') or {}).pop(team_id, None)
        _save(data, teams)


def set_member(username, team_id, role):
    """Put an account in a team with a role; ``role=None`` takes it out."""
    with _lock:
        data = _read()
        teams = _teams(data)
        if team_id not in teams:
            raise TeamError(f'No team called {team_id}.')
        user = (data.get('auth_users') or {}).get((username or '').lower())
        if not user:
            raise TeamError(f'No user called {username}.')
        memberships = user.setdefault('teams', {})
        if role is None:
            memberships.pop(team_id, None)
        else:
            try:
                memberships[team_id] = roles.validate(role)
            except roles.RoleError as exc:
                raise TeamError(str(exc)) from None
        _save(data, teams)   # also writes the defaults once someone uses them
