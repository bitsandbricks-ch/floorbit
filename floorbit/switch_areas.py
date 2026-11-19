"""Which seats each switch serves (issue #948, docs/switch-areas.md).

A switch's area comes from three sources, strongest first:

- **Manual**: the crew pins a switch to blocks, rows or single seats, or excludes it. A pin wins.
- **Learned**: a seat mapped to one of the switch's ports (seat walk, check-in) or patched to it in
  the patch plan puts that seat on the switch.
- **Plan position**: a switch drawn inside a block's area, the aisles between its rows included,
  serves the whole block. A switch outside every block is not guessed: it is a to-do.

Mike decided that the crew works a row at a time (rows, not blocks, are walked, patched and fed), so
the finer unit here is a row; the issue's "sections" are rows. A row whose seats are all learned on
one switch is offered as a pin (``suggest``).

When the sources disagree the switch lists the **drift**; nothing is picked silently. The check-in
lookup asks a seat's own switches first (floorbit/checkin_lookup.py ``candidates``).

Stored per event in its data as ``switch_areas``: ``{switch name: {blocks, rows, seats, exclude}}``.
"""
import math

from . import seat_gaps, seat_names

KEY = 'switch_areas'
MAX_SEATS = 500          # single seats pinned to one switch
MARGIN = 0.5             # seats around a block that still count as inside it (a switch at its edge)


class AreaError(ValueError):
    status = 400


# ── where things are on the plan ─────────────────────────────────────────────────────────────

def _inside(block, x, y):
    """Whether a point (plan %) lies in the block's area, turned like the block, aisles included."""
    from .block_merge import PLAN_SEATS_H, PLAN_SEATS_W
    try:
        _, w = seat_gaps.offsets(block.get('col_gaps'), int(block['cols']))
        _, h = seat_gaps.offsets(block.get('row_gaps'), int(block['rows']))
        cx, cy = float(block['x']) / 100 * PLAN_SEATS_W, float(block['y']) / 100 * PLAN_SEATS_H
    except (KeyError, TypeError, ValueError):
        return False
    px, py = float(x) / 100 * PLAN_SEATS_W, float(y) / 100 * PLAN_SEATS_H
    a = math.radians(-(int(block.get('rotation') or 0) % 360))
    dx, dy = px - cx, py - cy
    lx, ly = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    return abs(lx) <= w / 2 + MARGIN and abs(ly) <= h / 2 + MARGIN


def _plan_blocks(dev, blocks):
    if dev.get('x') is None or dev.get('y') is None:
        return []
    return [b['id'] for b in blocks
            if (b.get('hall_id') or None) == (dev.get('hall_id') or None) and _inside(b, dev['x'], dev['y'])]


# ── the sources ──────────────────────────────────────────────────────────────────────────────

def _learned(data):
    """{switch (lower case): {seat: 'walk' | 'checkin' | 'cable'}}."""
    from integrations import checkin

    from . import cables
    out = {}
    for c in cables.all_cables(data):
        if c.get('switch') and c.get('seat'):
            out.setdefault(str(c['switch']).lower(), {})[str(c['seat']).upper()] = 'cable'
    for seat, port in checkin.learned_ports().items():
        if port.get('switch'):
            out.setdefault(str(port['switch']).lower(), {})[str(seat).upper()] = port.get('source') or 'checkin'
    return out


def _manual(data):
    raw = data.get(KEY)
    return {str(k).lower(): v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def _switches(data):
    from . import inventory
    return [d for d in inventory.devices(data) if d.get('role') == 'switch' and d.get('name')]


def overview(data=None):
    """Every switch with what it serves: ``{name, serves: {blocks, rows, seats}, how, manual,
    learned, plan_blocks, drift, suggest, todo}``, switches in name order."""
    from .store import load_data
    data = load_data() if data is None else data
    rows = seat_names.hall_rows(data)
    blocks = [b for b in data.get('seat_blocks') or [] if b.get('id')]
    block_label = {b['id']: seat_names.label(b) for b in blocks}
    row_of = {s: r for r in rows for s in r['seats']}
    row_by_id = {r['id']: r for r in rows}
    learned, manual = _learned(data), _manual(data)
    out = []
    for dev in sorted(_switches(data), key=lambda d: d['name'].lower()):
        key = dev['name'].lower()
        pin = manual.get(key) or {}
        pin = {'blocks': [b for b in pin.get('blocks') or [] if b in block_label],
               'rows': [r for r in pin.get('rows') or [] if r in row_by_id],
               'seats': [s for s in pin.get('seats') or [] if s in row_of], 'exclude': bool(pin.get('exclude'))}
        seats = learned.get(key, {})
        plan = _plan_blocks(dev, blocks)
        pinned = bool(pin['blocks'] or pin['rows'] or pin['seats'])
        if pin['exclude']:
            how, serves = 'excluded', {'blocks': [], 'rows': [], 'seats': []}
        elif pinned:
            how, serves = 'manual', {k: pin[k] for k in ('blocks', 'rows', 'seats')}
        else:
            learned_rows = sorted({row_of[s]['id'] for s in seats if s in row_of})
            how = 'learned' if seats else 'plan' if plan else 'todo'
            serves = {'blocks': plan, 'rows': learned_rows, 'seats': sorted(seats)}
        out.append({'name': dev['name'], 'id': dev['id'], 'how': how, 'serves': serves, 'manual': pin,
                    'learned': [{'seat': s, 'source': src} for s, src in sorted(seats.items())],
                    'plan_blocks': plan, 'todo': how == 'todo',
                    'drift': _drift(pin, pinned, seats, plan, row_of, block_label),
                    'suggest': _suggest(pin, seats, rows)})
    return {'switches': out, 'blocks': [{'id': b, 'label': lab} for b, lab in block_label.items()]}


def _drift(pin, pinned, seats, plan, row_of, block_label):
    """Where the sources disagree, each ``{kind, seats?, block?}``; the crew decides."""
    if pin['exclude']:
        return [{'kind': 'excluded_learned', 'seats': sorted(seats)}] if seats else []
    out = []
    if pinned:
        mine = set(pin['seats'])
        for r in pin['rows']:
            mine |= {s for s, row in row_of.items() if row['id'] == r}
        for b in pin['blocks']:
            mine |= {s for s, row in row_of.items() if row['block'] == b}
        outside = sorted(s for s in seats if s not in mine)
        if outside:
            out.append({'kind': 'learned_outside_pin', 'seats': outside})
        pinned_blocks = set(pin['blocks']) | {row_of[s]['block'] for s in mine if s in row_of}
        for b in plan:
            if b not in pinned_blocks:
                out.append({'kind': 'drawn_elsewhere', 'block': block_label.get(b, b)})
    elif plan:
        outside = sorted(s for s in seats if s in row_of and row_of[s]['block'] not in plan)
        if outside:
            out.append({'kind': 'learned_outside_plan', 'seats': outside})
    return out


def _suggest(pin, seats, rows):
    """Rows all of whose seats are learned on this switch and not pinned yet: one click to pin."""
    if pin['exclude']:
        return []
    return [{'id': r['id'], 'name': r['name'], 'block_label': r['block_label']} for r in rows
            if r['seats'] and r['id'] not in pin['rows'] and all(s in seats for s in r['seats'])]


# ── changes ──────────────────────────────────────────────────────────────────────────────────

def pin(switch, body, data):
    """Sets a switch's manual area (``{blocks, rows, seats, exclude}``); an empty one removes it."""
    body = body if isinstance(body, dict) else {}
    names = {d['name'].lower(): d['name'] for d in _switches(data)}
    key = str(switch or '').lower()
    if key not in names:
        raise AreaError('No such switch in the inventory.')
    known_blocks = {b['id'] for b in data.get('seat_blocks') or [] if b.get('id')}
    rows = seat_names.hall_rows(data)
    known_rows = {r['id'] for r in rows}
    known_seats = {s for r in rows for s in r['seats']}

    def pick(field, known, upper=False):
        value = body.get(field) or []
        if not isinstance(value, list):
            raise AreaError('Pick blocks, rows and seats from the lists.')
        picked = list(dict.fromkeys(str(v).strip().upper() if upper else str(v).strip()
                                    for v in value if str(v).strip()))
        if any(v not in known for v in picked):
            raise AreaError('That is not on the floor plan any more.')
        return picked
    area = {'blocks': pick('blocks', known_blocks), 'rows': pick('rows', known_rows),
            'seats': pick('seats', known_seats, upper=True)[:MAX_SEATS], 'exclude': bool(body.get('exclude'))}
    stored = _manual(data)
    if area['exclude'] or area['blocks'] or area['rows'] or area['seats']:
        stored[key] = area
    else:
        stored.pop(key, None)
    data[KEY] = stored
    return area


def switches_for(seats, data):
    """The switches that serve any of these seats, by their area (pins, learned, plan position)."""
    wanted = {str(s).upper() for s in seats}
    if not wanted:
        return []
    rows = seat_names.hall_rows(data)
    row_of = {s: r for r in rows for s in r['seats']}
    out = []
    for sw in overview(data)['switches']:
        serves = sw['serves']
        mine = set(serves['seats'])
        for s in wanted:
            r = row_of.get(s)
            if r and (r['id'] in serves['rows'] or r['block'] in serves['blocks']):
                mine.add(s)
        if mine & wanted:
            out.append(sw['name'])
    return out


def drift_for(seat, switch, data):
    """Whether a port just found for ``seat`` on ``switch`` disagrees with the switch's area (issue
    #1094): ``{kind: 'pin' | 'plan' | 'excluded', switch, area: [row or block names], row}`` or None.
    Shown right where it is found (seat walk), so the crew fixes the pin or the patch on the spot."""
    seat = str(seat or '').upper()
    rows = seat_names.hall_rows(data)
    row = next((r for r in rows if seat in r['seats']), None)
    if not row:
        return None
    view = overview(data)
    sw = next((s for s in view['switches'] if s['name'].lower() == str(switch or '').lower()), None)
    if not sw:
        return None
    labels = {b['id']: b['label'] for b in view['blocks']}
    names = {r['id']: f"{r['block_label']} {r['name']}".strip() for r in rows}
    here = f"{row['block_label']} {row['name']}".strip()
    if sw['how'] == 'excluded':
        return {'kind': 'excluded', 'switch': sw['name'], 'area': [], 'row': here}
    if sw['how'] == 'manual':
        pin = sw['manual']
        if seat in pin['seats'] or row['id'] in pin['rows'] or row['block'] in pin['blocks']:
            return None
        area = [labels.get(b, b) for b in pin['blocks']] + [names.get(r, r) for r in pin['rows']] + pin['seats']
        return {'kind': 'pin', 'switch': sw['name'], 'area': area, 'row': here}
    if sw['plan_blocks'] and row['block'] not in sw['plan_blocks']:
        return {'kind': 'plan', 'switch': sw['name'], 'area': [labels.get(b, b) for b in sw['plan_blocks']],
                'row': here}
    return None
