"""Cables and patching (issue #97): which switch port goes to which patch panel port and seat, with
printable labels for both ends. See docs/cables.md.

A cable is ``switch port -> patch panel port -> seat``; the panel and the seat are optional (a seat
patched straight into a switch has no panel). Cables are kept in data.json under ``cables``. Ones
typed in Floorbit are the crew's (``source: floorbit``); ones read from NetBox (any inventory plugin
with ``cables()``) are ``source: import`` and each import replaces the last, so NetBox stays the source
for them. A crew cable on the same switch port wins over an imported one.

Each cable has a short label (``C-0001`` unless one is given) printed on both ends with a QR code
that opens the cable in Floorbit.

A whole seat block is patched in one go (issue #473): "switch X from port Gi1/0/1, along the rows
(or snaking), from the first seat (or the last)". ``plan_block`` shows which seat gets which port and
what clashes; ``add_block`` makes the cables, all or none. They remember their block, so a block
can be planned again (shifted by a port, another switch) with ``replace``.
"""
import re
import threading
import time
import uuid

from . import agent_link
from .plugins import PluginError
from .store import load_data, save_data

KEY = 'cables'
MAX_CABLES = 5000
PORT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/._:-]{0,47}$')
LABEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,23}$')
FIELDS = ('label', 'switch', 'port', 'panel', 'panel_port', 'seat', 'color', 'length_m', 'type', 'speed', 'note')
LIMITS = {'switch': 80, 'panel': 40, 'panel_port': 16, 'seat': 16, 'color': 20, 'note': 200}
_lock = threading.Lock()


class CableError(ValueError):
    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def all_cables(data=None):
    data = load_data() if data is None else data
    return list(data.get(KEY) or [])


def _next_label(cables):
    used = {c.get('label') for c in cables}
    n = len(cables) + 1
    while f'C-{n:04d}' in used:
        n += 1
    return f'C-{n:04d}'


def clean(body, cables, current=None):
    """A cable from the browser or a plugin, checked. Raises CableError."""
    out = {f: _text(body.get(f), LIMITS[f]) for f in LIMITS}
    out['seat'] = out['seat'].upper()
    port = _text(body.get('port'), 48)
    if not out['switch'] or not PORT_RE.match(port):
        raise CableError('A cable needs its switch and a port name, for example Gi1/0/3.')
    out['port'] = port
    if out['panel_port'] and not out['panel']:
        raise CableError('Name the patch panel for that panel port.')
    length = body.get('length_m')
    if length in (None, ''):
        out['length_m'] = None
    else:
        try:
            out['length_m'] = round(float(length), 1)
        except (TypeError, ValueError):
            raise CableError('The length is a number of metres.') from None
        if not 0 < out['length_m'] <= 500:
            raise CableError('The length is 0.1 to 500 metres.')
    from .links import SPEEDS, TYPES
    out['type'] = body.get('type') or ''
    if out['type'] not in ('', *TYPES):
        raise CableError('The type is cat5e, cat6, cat6a, fiber-sm, fiber-mm or dac.')
    speed = body.get('speed')
    try:
        out['speed'] = None if speed in (None, '') else int(speed)
    except (TypeError, ValueError):
        out['speed'] = 0
    if out['speed'] is not None and out['speed'] not in SPEEDS:
        raise CableError('The speed is 1, 10, 25, 40 or 100 (Gbit/s).')
    label = _text(body.get('label'), 24)
    others = [c for c in cables if c is not current]
    if label:
        if not LABEL_RE.match(label):
            raise CableError('A label is up to 24 letters, digits, spaces, . _ / # or -.')
        if any(c.get('label', '').lower() == label.lower() for c in others):
            raise CableError(f'Another cable already has the label {label}.')
    else:
        label = current.get('label') if current else _next_label(cables)
    out['label'] = label
    # One cable per switch port: a second one is almost always a typo.
    if any(c['switch'].lower() == out['switch'].lower() and c['port'].lower() == port.lower() for c in others):
        raise CableError(f'{out["switch"]} {port} already has a cable.', 409)
    return out


def add(body, by):
    with _lock:
        data = load_data()
        cables = data.setdefault(KEY, [])
        if len(cables) >= MAX_CABLES:
            raise CableError(f'Floorbit keeps at most {MAX_CABLES} cables.')
        cable = {'id': uuid.uuid4().hex[:12], **clean(body, cables), 'source': 'floorbit',
                 'updated_at': time.time(), 'by': by}
        cables.append(cable)
        save_data(data)
    return cable


def update(cable_id, body, by):
    with _lock:
        data = load_data()
        cables = data.setdefault(KEY, [])
        cable = next((c for c in cables if c['id'] == cable_id), None)
        if not cable:
            raise CableError('No such cable.', 404)
        if cable.get('source') == 'import':
            raise CableError(f"This cable comes from {cable.get('plugin') or 'NetBox'}: change it there and import "
                             'again.', 409)
        cable.update(clean({**cable, **body}, cables, current=cable), updated_at=time.time(), by=by)
        save_data(data)
    return cable


def delete(cable_id):
    with _lock:
        data = load_data()
        cables = data.get(KEY) or []
        kept = [c for c in cables if c['id'] != cable_id]
        if len(kept) == len(cables):
            return False
        data[KEY] = kept
        save_data(data)
    return True


def sources(registry):
    """Plugins that are on and can tell Floorbit about cables."""
    out = []
    for spec in registry.feeders('inventory'):
        cls = spec.plugin_class()
        if cls is not None and hasattr(cls, 'cables'):
            out.append(spec)
    return out


def import_from(registry, by):
    """Replace the cables from plugins with what they have now. Returns (count, errors)."""
    found, errors, answered = [], [], set()
    if agent_link.active():
        # A hosted Floorbit: the local agent asks the event's NetBox. A plugin it answered for
        # isn't asked here too, since this side can't reach it.
        try:
            feeds = agent_link.cable_feeds()
        except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
            feeds = []
            errors.append(f'Local agent: {exc}')
        for feed in feeds:
            if 'error' in feed:
                errors.append(f"{feed['name']} (local agent): {feed['error']}")
            else:
                found += [(feed['name'], c) for c in feed['items']]
                answered.update({feed['name'], feed.get('base_name', feed['name'])})
    for spec in sources(registry):
        if spec.name in answered:
            continue
        try:
            found += [(spec.name, c) for c in registry.call(spec, 'cables') or []]
            answered.add(spec.name)
        except PluginError as exc:
            errors.append(f'{spec.name}: {exc}')
    if errors and not answered:
        raise CableError('; '.join(errors), 502)
    with _lock:
        data = load_data()
        # A source that failed this time keeps its last import: NetBox down for a minute must not
        # empty the cable list.
        kept = [c for c in data.get(KEY) or [] if c.get('source') != 'import' or c.get('plugin') not in answered]
        added, skipped = [], 0
        for plugin, raw in found:
            try:
                cable = clean(raw, kept + added)
            except CableError:
                skipped += 1   # one bad cable in NetBox must not stop the rest
                continue
            added.append({'id': uuid.uuid4().hex[:12], **cable, 'source': 'import', 'plugin': plugin,
                          'updated_at': time.time(), 'by': by})
        data[KEY] = (kept + added)[:MAX_CABLES]
        save_data(data)
    if skipped:
        errors.append(f'{skipped} cable(s) skipped: no switch port, or a switch port that already has a cable.')
    return len(added), errors


def matching(cables, q='', ids=None):
    words = [w for w in str(q or '').lower().split() if w]
    out = []
    for c in cables:
        if ids is not None and c['id'] not in ids:
            continue
        text = ' '.join(str(c.get(f) or '') for f in FIELDS).lower()
        if all(w in text for w in words):
            out.append(c)
    return out


def for_seat(seat, data=None):
    seat = str(seat or '').upper()
    return [c for c in all_cables(data) if c.get('seat') == seat]


# ── Labels ──────────────────────────────────────────────────────────────────────────────
COLS, ROWS = 3, 8
MX, MY = 20.0, 36.0


def route(c):
    parts = [f"{c['switch']} {c['port']}"]
    if c.get('panel'):
        parts.append(f"{c['panel']} {c.get('panel_port') or ''}".strip())
    if c.get('seat'):
        parts.append(f"Seat {c['seat']}")
    return ' > '.join(parts)


def labels_pdf(cables, base_url):
    """A4, 3 x 8 labels, two per cable (switch end, then the far end): the label big, a QR code
    that opens the cable, the end it goes on in bold and where the other end goes small."""
    import segno

    from . import pdf
    w = (pdf.A4[0] - 2 * MX) / COLS
    h = (pdf.A4[1] - 2 * MY) / ROWS
    items = [(c, end) for c in cables for end in ('switch', 'far')]
    pages = []
    per_page = COLS * ROWS
    for start in range(0, max(len(items), 1), per_page):
        page = pdf.Page()
        for k, (c, end) in enumerate(items[start:start + per_page]):
            x, y = MX + (k % COLS) * w, MY + (k // COLS) * h
            page.rect(x + 3, y + 3, w - 6, h - 6, stroke='#c9ced6')
            qr = segno.make(f"{base_url.rstrip('/')}/cables?cable={c['id']}", error='m')
            matrix = list(qr.matrix)
            size = min(h - 24, 62.0)
            cell = size / len(matrix)
            for r, line in enumerate(matrix):
                for col, dark in enumerate(line):
                    if dark:
                        page.rect(x + 9 + col * cell, y + 10 + r * cell, cell + 0.05, cell + 0.05, fill='#000000')
            tx, tw = x + 16 + size, w - size - 24
            page.text(tx, y + 26, pdf.fit(c['label'], 16, tw, bold=True), size=16, bold=True)
            here = f"{c['switch']} {c['port']}" if end == 'switch' else (
                f"Seat {c['seat']}" if c.get('seat') else f"{c.get('panel') or ''} {c.get('panel_port') or ''}".strip())
            page.text(tx, y + 42, pdf.fit(here or '-', 10, tw, bold=True), size=10, bold=True)
            # The other end(s), not the whole route: the end this label is on is already in bold.
            panel = f"{c.get('panel') or ''} {c.get('panel_port') or ''}".strip()
            if end == 'switch':
                there = ' > '.join(p for p in (panel, f"Seat {c['seat']}" if c.get('seat') else '') if p)
                there = f'to {there}' if there else ''
            else:
                there = f"from {c['switch']} {c['port']}" + (f' via {panel}' if panel and c.get('seat') else '')
            page.text(tx, y + 56, pdf.fit(there, 6.5, tw), size=6.5, color='#5b6370')
            if c.get('color') or c.get('length_m') or c.get('type') or c.get('speed'):
                extra = ' '.join(p for p in (c.get('color'), f"{c['length_m']:g} m" if c.get('length_m') else '',
                                             c.get('type') or '', f"{c['speed']}G" if c.get('speed') else '') if p)
                page.text(tx, y + 67, pdf.fit(extra, 6.5, tw), size=6.5, color='#5b6370')
        pages.append(page)
    return pdf.render(pages, title='Cable labels')


def csv_text(cables):
    from .planner import _csv
    lines = [','.join((*FIELDS, 'source'))]
    for c in cables:
        lines.append(','.join(_csv(c.get(f) if c.get(f) is not None else '') for f in (*FIELDS, 'source')))
    return '\n'.join(lines) + '\n'


# ── a seat block in one go (issue #473) ─────────────────────────────────────────────
PORT_NUMBER_RE = re.compile(r'^(.*?)(\d+)$')
MAX_BLOCK_SEATS = 1000


def _rows(text, count):
    """'2-3' or '2' or '' (all) -> the row numbers, counted from 1, top row first as drawn."""
    text = str(text or '').strip()
    if not text:
        return list(range(1, count + 1))
    m = re.match(r'^(\d+)\s*(?:-\s*(\d+))?$', text)
    if not m:
        raise CableError('Rows are a number or a range, for example 1-2.')
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    if not 1 <= first <= last <= count:
        raise CableError(f'This block has rows 1 to {count}.')
    return list(range(first, last + 1))


def plan_block(body, data=None):
    """Which seat gets which port: ``{"cables": [{seat, switch, port}], "clashes": [...]}``.

    ``body``: ``block`` (id), ``switch``, ``first_port`` (the port of the first seat; the last number
    counts up), ``order`` (``rows``: each row the same way; ``snake``: every other row back),
    ``reverse`` (start at the last seat), ``rows`` (``"1-2"``; all when empty)."""
    from .power import block_rows  # power reads cables' neighbours: imported late
    data = load_data() if data is None else data
    block = next((b for b in data.get('seat_blocks') or [] if b.get('id') == body.get('block')), None)
    if not block:
        raise CableError('Pick a seat block.', 404)
    switch = _text(body.get('switch'), LIMITS['switch'])
    if not switch:
        raise CableError('Pick the switch the block is patched to.')
    first = _text(body.get('first_port'), 48)
    m = PORT_NUMBER_RE.match(first)
    if not m or not PORT_RE.match(first):
        raise CableError('The first port ends in a number, for example Gi1/0/1.')
    prefix, start = m.group(1), int(m.group(2))
    order = body.get('order') or 'rows'
    if order not in ('rows', 'snake'):
        raise CableError('The order is rows or snake.')
    rows = block_rows(block)
    seats = []
    for i, r in enumerate(_rows(body.get('rows'), len(rows))):
        row = rows[r - 1]
        seats += list(reversed(row)) if order == 'snake' and i % 2 else row
    if body.get('reverse'):
        seats.reverse()
    if len(seats) > MAX_BLOCK_SEATS:
        raise CableError(f'At most {MAX_BLOCK_SEATS} seats at once.')
    width = len(m.group(2)) if m.group(2).startswith('0') else 0     # Eth01 -> Eth02, not Eth2
    planned = [{'seat': seat.upper(), 'switch': switch, 'port': f'{prefix}{start + n:0{width}d}',
                'block': block['id']} for n, seat in enumerate(seats)]
    return {'block': block.get('name') or '', 'cables': planned, 'clashes': _clashes(planned, all_cables(data))}


def _replaced(cable, planned_seats, block_id):
    """One of this block's own cables on a seat being planned again: it makes way, no clash."""
    return cable.get('block') == block_id and cable.get('source') == 'floorbit' and cable.get('seat') in planned_seats


def _clashes(planned, cables):
    """Cables in the way: on a planned port, or on a planned seat, that aren't being planned again."""
    from .syslog import canonical_port
    if not planned:
        return []
    block_id, planned_seats = planned[0]['block'], {p['seat'] for p in planned}
    ports = {(c['switch'].lower(), canonical_port(c['port'])): c for c in cables}
    seats = {}
    for c in cables:
        if c.get('seat'):
            seats.setdefault(c['seat'], c)
    out = []
    for p in planned:
        on_port = ports.get((p['switch'].lower(), canonical_port(p['port'])))
        if on_port and not _replaced(on_port, planned_seats, block_id):
            out.append({'seat': p['seat'], 'port': p['port'], 'kind': 'port', 'cable': on_port['label'],
                        'other_seat': on_port.get('seat') or '', 'imported': on_port.get('source') == 'import'})
        on_seat = seats.get(p['seat'])
        if on_seat and not _replaced(on_seat, planned_seats, block_id) and on_seat is not on_port:
            out.append({'seat': p['seat'], 'port': p['port'], 'kind': 'seat', 'cable': on_seat['label'],
                        'other_port': f"{on_seat['switch']} {on_seat['port']}",
                        'imported': on_seat.get('source') == 'import'})
    return out


def add_block(body, by, replace=False):
    """Make the planned cables, all or none. This block's own cables on these seats make way. Other
    cables in the way stop it (409), unless ``replace``: then the crew's go too; imported ones
    always stop it (NetBox is their source). Returns ``(plan, removed)``."""
    with _lock:
        data = load_data()
        plan = plan_block(body, data)
        cables = data.setdefault(KEY, [])
        if any(c['imported'] for c in plan['clashes']):
            raise CableError('Some of these ports or seats have cables from NetBox: change them there first.', 409)
        if plan['clashes'] and not replace:
            raise CableError(f"{len(plan['clashes'])} ports or seats already have a cable.", 409)
        if not plan['cables']:
            return plan, 0
        block_id, planned_seats = plan['cables'][0]['block'], {p['seat'] for p in plan['cables']}
        in_way = {c['cable'] for c in plan['clashes']}
        kept = [c for c in cables if not _replaced(c, planned_seats, block_id) and c['label'] not in in_way]
        removed = len(cables) - len(kept)
        if len(kept) + len(plan['cables']) > MAX_CABLES:
            raise CableError(f'Floorbit keeps at most {MAX_CABLES} cables.')
        now = time.time()
        for p in plan['cables']:
            kept.append({'id': uuid.uuid4().hex[:12], **clean({**p, 'label': _next_label(kept)}, kept),
                         'block': block_id, 'source': 'floorbit', 'updated_at': now, 'by': by})
        data[KEY] = kept
        save_data(data)
    return plan, removed


def _crew(cable):
    return cable.get('source') != 'import'


def assign(body, by):
    """Seat X is on switch port P, as the crew found it (walking the row, or a machine on a port no
    cable explained). The seat's own cable moves to P, or a new one is made. P's cable without a seat
    (infrastructure) is taken over. When P has another seat's cable: 409 naming that seat, unless
    ``swap``: then the two seats trade ports (the other gets this seat's old one, or none).

    Returns ``{"cable", "changed": [labels], "other_seat"}``."""
    from .syslog import canonical_port
    seat = _text(body.get('seat'), LIMITS['seat']).upper()
    if not seat:
        raise CableError('Name the seat.')
    with _lock:
        data = load_data()
        cables = data.setdefault(KEY, [])
        checked = clean({'switch': body.get('switch'), 'port': body.get('port')}, [])
        where = {'switch': checked['switch'], 'port': checked['port'], 'seat': seat}
        key = (where['switch'].lower(), canonical_port(where['port']))
        at_port = next((c for c in cables if _crew(c) and (c['switch'].lower(), canonical_port(c['port'])) == key),
                       None)
        mine = next((c for c in cables if _crew(c) and (c.get('seat') or '').upper() == seat), None)
        if at_port is not None and at_port is mine:
            return {'cable': mine, 'changed': [], 'other_seat': ''}
        other = (at_port.get('seat') or '').upper() if at_port else ''
        if other and not body.get('swap'):
            raise CableError(f"{where['switch']} {where['port']} is {other}'s port.", 409, other_seat=other)
        now, changed = time.time(), []
        if at_port is not None:
            if mine is not None and other:
                mine.update(seat=other, updated_at=now, by=by)
                changed.append(mine['label'])
            elif mine is not None:
                cables.remove(mine)          # the seat moved to the infrastructure cable's port
                changed.append(mine['label'])
            at_port.update(seat=seat, updated_at=now, by=by)
            cable = at_port
        elif mine is not None:
            mine.update(switch=where['switch'], port=where['port'], updated_at=now, by=by)
            cable = mine
        else:
            if len(cables) >= MAX_CABLES:
                raise CableError(f'Floorbit keeps at most {MAX_CABLES} cables.')
            cable = {'id': uuid.uuid4().hex[:12], **clean({**where, 'block': body.get('block')}, cables),
                     'source': 'floorbit', 'updated_at': now, 'by': by}
            if body.get('block'):
                cable['block'] = str(body['block'])[:40]
            cables.append(cable)
        changed.insert(0, cable['label'])
        save_data(data)
    return {'cable': cable, 'changed': changed, 'other_seat': other}


def port_seats(data=None):
    """{(switch lowercase, canonical port): seat} from the cables that end at a seat."""
    from .syslog import canonical_port
    return {(c['switch'].lower(), canonical_port(c['port'])): c['seat']
            for c in all_cables(data) if c.get('seat')}
