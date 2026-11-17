"""Locked items on the floor plan: the editor keeps them where they are (no dragging, nudging,
reshaping, turning or deleting) until someone unlocks them, so a hall's walls and stage don't move
while the seats around them are laid out.

``data['plan_locks']`` is ``[{'hall_id', 'kind', 'id'}]``, with the editor's item references
(frontend/src/pages/plan/edit/geometry.ts ``ItemRef``), as in floorbit/plan_groups.py. Locks whose
item is gone stay and are skipped, so an undone delete comes back locked.
"""
from . import halls

KEY = 'plan_locks'
KINDS = ('block', 'mark', 'switch', 'panel', 'board')
ID_MAX = 120
MAX_LOCKS = 5000


class LockError(ValueError):
    pass


def _items(value):
    if not isinstance(value, list) or not value:
        raise LockError('items is a list of items with a kind and an id')
    out = []
    for m in value:
        if not isinstance(m, dict) or m.get('kind') not in KINDS:
            raise LockError('A locked item is a seat block, mark, switch, patch panel or distribution board')
        ref = str(m.get('id') or '').strip()
        if not ref or len(ref) > ID_MAX:
            raise LockError('A locked item needs an id')
        if (m['kind'], ref) not in {(o['kind'], o['id']) for o in out}:
            out.append({'kind': m['kind'], 'id': ref})
    return out


def locks(data, hall_id):
    """The hall's locked items, ``[{kind, id}]``."""
    ids = {h['id'] for h in halls.halls(data)}
    return [{'kind': x['kind'], 'id': x['id']} for x in data.get(KEY) or []
            if isinstance(x, dict) and halls.hall_of(x, data, ids) == hall_id]


def set_locked(data, hall_id, items, locked):
    """Locks (or unlocks) ``items`` in the hall; returns the hall's locks after."""
    try:
        hall_id = halls.check_id(data, hall_id)
    except halls.HallError as exc:
        raise LockError(str(exc)) from None
    if not isinstance(locked, bool):
        raise LockError('locked is true or false')
    wanted = _items(items)
    keys = {(m['kind'], m['id']) for m in wanted}
    ids = {h['id'] for h in halls.halls(data)}
    kept = [x for x in data.get(KEY) or [] if isinstance(x, dict)
            and not (halls.hall_of(x, data, ids) == hall_id and (x.get('kind'), x.get('id')) in keys)]
    if locked:
        kept += [{'hall_id': hall_id, **m} for m in wanted]
        if len(kept) > MAX_LOCKS:
            raise LockError(f'At most {MAX_LOCKS} locked items on the plan')
    data[KEY] = kept
    return locks(data, hall_id)
