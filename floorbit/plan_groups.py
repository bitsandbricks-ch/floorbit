"""Groups on the floor plan: any items of one hall (seat blocks, labels, walls, zones, icons,
switches, patch panels, distribution boards) that the editor selects and moves as one.

``data['plan_groups']`` is ``[{'id', 'hall_id', 'name', 'members': [{'kind', 'id'}]}]``. Members are
the editor's item references (frontend/src/pages/plan/edit/geometry.ts ``ItemRef``); a patch panel's
id is its name. An item is in at most one group: joining a new group takes it out of the old one.

Members whose item is gone are left in place and skipped by the editor, so a delete that is undone
doesn't break the group. Seat blocks still read their older ``group`` field (the classic editor's).
"""
import uuid

from . import halls

KEY = 'plan_groups'
KINDS = ('block', 'mark', 'switch', 'panel', 'board')
NAME_MAX = 40
ID_MAX = 120
MAX_MEMBERS = 500
MAX_GROUPS = 500


class GroupError(ValueError):
    pass


def _members(value):
    if not isinstance(value, list):
        raise GroupError('members is a list of items with a kind and an id')
    out, seen = [], set()
    for m in value:
        if not isinstance(m, dict) or m.get('kind') not in KINDS:
            raise GroupError('A member is a seat block, mark, switch, patch panel or distribution board')
        ref = str(m.get('id') or '').strip()
        if not ref or len(ref) > ID_MAX:
            raise GroupError('A member needs an id')
        if (m['kind'], ref) not in seen:
            seen.add((m['kind'], ref))
            out.append({'kind': m['kind'], 'id': ref})
    if len(out) < 2:
        raise GroupError('A group has at least two items')
    if len(out) > MAX_MEMBERS:
        raise GroupError(f'A group has at most {MAX_MEMBERS} items')
    return out


def _name(value):
    name = str(value or '').strip()
    if len(name) > NAME_MAX:
        raise GroupError(f'A group name has at most {NAME_MAX} characters')
    return name


def all_groups(data, hall_id=None):
    """The groups, each with its hall written out; with ``hall_id`` only that hall's."""
    ids = {h['id'] for h in halls.halls(data)}
    out = []
    for g in data.get(KEY) or []:
        if not isinstance(g, dict):
            continue
        hall = halls.hall_of(g, data, ids)
        if hall_id is None or hall == hall_id:
            out.append({**g, 'hall_id': hall})
    return out


def _take_out(data, hall_id, members, keep=None):
    """Takes ``members`` out of the hall's other groups; a group left with one item goes."""
    taken = {(m['kind'], m['id']) for m in members}
    ids = {h['id'] for h in halls.halls(data)}
    out = []
    for g in data.get(KEY) or []:
        if g.get('id') != keep and halls.hall_of(g, data, ids) == hall_id:
            g = {**g, 'members': [m for m in g.get('members') or [] if (m.get('kind'), m.get('id')) not in taken]}
            if len(g['members']) < 2:
                continue
        out.append(g)
    data[KEY] = out


def add(data, body):
    if not isinstance(body, dict):
        raise GroupError('Expected a JSON object')
    if len(data.get(KEY) or []) >= MAX_GROUPS:
        raise GroupError(f'At most {MAX_GROUPS} groups on the plan')
    try:
        hall_id = halls.check_id(data, body.get('hall_id'))
    except halls.HallError as exc:
        raise GroupError(str(exc)) from None
    group = {'id': str(body.get('id') or '') or uuid.uuid4().hex[:12], 'hall_id': hall_id,
             'name': _name(body.get('name')), 'members': _members(body.get('members'))}
    if len(group['id']) > ID_MAX or any(g.get('id') == group['id'] for g in data.get(KEY) or []):
        group['id'] = uuid.uuid4().hex[:12]
    _take_out(data, hall_id, group['members'])
    data.setdefault(KEY, []).append(group)
    return group


def change(data, group_id, body):
    if not isinstance(body, dict):
        raise GroupError('Expected a JSON object')
    for g in all_groups(data):
        if g.get('id') == group_id:
            new = {**g, 'name': _name(body['name']) if 'name' in body else g.get('name', '')}
            if 'members' in body:
                new['members'] = _members(body['members'])
                _take_out(data, g['hall_id'], new['members'], keep=group_id)
            data[KEY] = [new if x.get('id') == group_id else x for x in data.get(KEY) or []]
            return new
    return None


def replace(data, hall_id, groups):
    """Sets the hall's groups to ``groups`` at once (the editor's undo and redo)."""
    try:
        hall_id = halls.check_id(data, hall_id)
    except halls.HallError as exc:
        raise GroupError(str(exc)) from None
    if not isinstance(groups, list):
        raise GroupError('groups is a list')
    ids = {h['id'] for h in halls.halls(data)}
    data[KEY] = [g for g in data.get(KEY) or [] if isinstance(g, dict) and halls.hall_of(g, data, ids) != hall_id]
    for g in groups:
        add(data, {**(g if isinstance(g, dict) else {}), 'hall_id': hall_id})
    return all_groups(data, hall_id)


def remove(data, group_id):
    before = len(data.get(KEY) or [])
    data[KEY] = [g for g in data.get(KEY) or [] if g.get('id') != group_id]
    return len(data[KEY]) != before
