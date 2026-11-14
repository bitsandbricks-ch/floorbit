"""Cables and patching (issue #97): which switch port goes to which patch panel port and seat, with
printable labels for both ends. See docs/cables.md.

A cable is ``switch port -> patch panel port -> seat``; the panel and the seat are optional (a seat
patched straight into a switch has no panel). Cables are kept in data.json under ``cables``. Ones
typed in Floorbit are the crew's (``source: floorbit``); ones read from NetBox (any inventory plugin
with ``cables()``) are ``source: import`` and each import replaces the last, so NetBox stays the source
for them. A crew cable on the same switch port wins over an imported one.

Each cable has a short label (``C-0001`` unless one is given) printed on both ends with a QR code
that opens the cable in Floorbit.
"""
import re
import threading
import time
import uuid

from .plugins import PluginError
from .store import load_data, save_data

KEY = 'cables'
MAX_CABLES = 5000
PORT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/._:-]{0,47}$')
LABEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,23}$')
FIELDS = ('label', 'switch', 'port', 'panel', 'panel_port', 'seat', 'color', 'length_m', 'note')
LIMITS = {'switch': 80, 'panel': 40, 'panel_port': 16, 'seat': 16, 'color': 20, 'note': 200}
_lock = threading.Lock()


class CableError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


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
    for spec in sources(registry):
        try:
            found += [(spec, c) for c in registry.call(spec, 'cables') or []]
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
        for spec, raw in found:
            try:
                cable = clean(raw, kept + added)
            except CableError:
                skipped += 1   # one bad cable in NetBox must not stop the rest
                continue
            added.append({'id': uuid.uuid4().hex[:12], **cable, 'source': 'import', 'plugin': spec.name,
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
            if c.get('color') or c.get('length_m'):
                extra = ' '.join(p for p in (c.get('color'), f"{c['length_m']:g} m" if c.get('length_m') else '') if p)
                page.text(tx, y + 67, pdf.fit(extra, 6.5, tw), size=6.5, color='#5b6370')
        pages.append(page)
    return pdf.render(pages, title='Cable labels')


def csv_text(cables):
    from .planner import _csv
    lines = ['label,switch,port,panel,panel_port,seat,color,length_m,note,source']
    for c in cables:
        lines.append(','.join(_csv(c.get(f) if c.get(f) is not None else '') for f in (*FIELDS, 'source')))
    return '\n'.join(lines) + '\n'
