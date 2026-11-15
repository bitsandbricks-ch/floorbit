"""Gear loans (issue #36). See docs/gear.md.

The gear itself lives in NetBox (or is added by hand in Floorbit's inventory): Floorbit keeps no stock.
What it adds is who has which piece right now: a switch lent to a tech, an access point out in hall 2.
Each piece gets a QR label that opens it on the phone, to check it out or back in with one tap.

Kept in data.json under ``loans``: ``{"out": {device_id: {...}}, "log": [...]}``. The log (newest
``MAX_LOG``) is the history the teardown checklist (#37) and the event report can read.
"""
import threading
import time

from .store import load_data, save_data

KEY = 'loans'
MAX_LOG = 2000
MAX_TO = 80
MAX_NOTE = 300

_lock = threading.Lock()


class GearError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _stored(data):
    raw = data.get(KEY)
    raw = raw if isinstance(raw, dict) else {}
    return {'out': dict(raw.get('out') or {}), 'log': list(raw.get('log') or [])}


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def items(data=None):
    """Every piece of gear with its loan, if it is out."""
    from . import inventory
    data = data if data is not None else load_data()
    out = _stored(data)['out']
    rows = []
    for d in inventory.devices(data):
        rows.append({'id': d['id'], 'name': d.get('name') or '', 'role': d.get('role') or 'other',
                     'model': d.get('model') or '', 'serial': d.get('serial') or '', 'origin': d.get('origin'),
                     'placed': d.get('x') is not None, 'loan': out.get(d['id'])})
    return sorted(rows, key=lambda r: (r['role'], r['name'].lower()))


def log(data=None, limit=200):
    return _stored(data if data is not None else load_data())['log'][:limit]


def _device(data, device_id):
    from . import inventory
    dev = inventory.find(data, device_id)
    if not dev:
        raise GearError('No such piece of gear.', 404)
    return dev


def check_out(device_id, body, by, now=None):
    to = _text(body.get('to'), MAX_TO)
    if not to:
        raise GearError('Say who or where it goes to: a person or an area.')
    kind = body.get('kind') if body.get('kind') in ('person', 'area') else 'person'
    now = time.time() if now is None else now
    with _lock:
        data = load_data()
        dev = _device(data, device_id)
        state = _stored(data)
        if device_id in state['out']:
            raise GearError(f"{dev.get('name')} is already out with {state['out'][device_id]['to']}. "
                            'Check it in first.', 409)
        loan = {'to': to, 'kind': kind, 'by': by, 'at': now, 'note': _text(body.get('note'), MAX_NOTE)}
        state['out'][device_id] = loan
        state['log'] = [{'device_id': device_id, 'name': dev.get('name'), 'action': 'out', 'to': to, 'kind': kind,
                         'by': by, 'at': now, 'note': loan['note']}, *state['log']][:MAX_LOG]
        data[KEY] = state
        save_data(data)
        return loan


def check_in(device_id, body, by, now=None):
    now = time.time() if now is None else now
    with _lock:
        data = load_data()
        dev = _device(data, device_id)
        state = _stored(data)
        loan = state['out'].pop(device_id, None)
        if not loan:
            raise GearError(f"{dev.get('name')} is not checked out.", 409)
        state['log'] = [{'device_id': device_id, 'name': dev.get('name'), 'action': 'in', 'to': loan['to'],
                         'kind': loan['kind'], 'by': by, 'at': now, 'note': _text(body.get('note'), MAX_NOTE),
                         'out_for': round(now - loan['at'])}, *state['log']][:MAX_LOG]
        data[KEY] = state
        save_data(data)
        return {'device_id': device_id, 'returned_from': loan['to']}


def outstanding(data=None):
    return [r for r in items(data) if r['loan']]


def labels_pdf(rows, base_url):
    """A4 sheet of QR labels, 4 x 8: the QR opens the piece on the gear page."""
    import segno

    from . import pdf
    cols, rows_per = 4, 8
    mx, my = 24.0, 36.0
    w = (pdf.A4[0] - 2 * mx) / cols
    h = (pdf.A4[1] - 2 * my) / rows_per
    pages = []
    for start in range(0, max(len(rows), 1), cols * rows_per):
        page = pdf.Page()
        for k, item in enumerate(rows[start:start + cols * rows_per]):
            x, y = mx + (k % cols) * w, my + (k // cols) * h
            page.rect(x + 3, y + 3, w - 6, h - 6, stroke='#c9ced6')
            qr = segno.make(f"{base_url.rstrip('/')}/gear?item={item['id']}", error='m')
            matrix = list(qr.matrix)
            size = h - 30
            cell = size / len(matrix)
            for r, line in enumerate(matrix):
                for c, dark in enumerate(line):
                    if dark:
                        page.rect(x + 10 + c * cell, y + 8 + r * cell, cell + 0.05, cell + 0.05, fill='#000000')
            tx = x + 16 + size
            page.text(tx, y + 24, pdf.fit(item['name'], 10, w - size - 22), size=10, bold=True)
            page.text(tx, y + 38, pdf.fit(item['model'] or item['role'], 7, w - size - 22), size=7, color='#5b6370')
            if item['serial']:
                page.text(tx, y + 50, pdf.fit(item['serial'], 7, w - size - 22), size=7, color='#5b6370')
        pages.append(page)
    return pdf.render(pages, title='Gear labels')
