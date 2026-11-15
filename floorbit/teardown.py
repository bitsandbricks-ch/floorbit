"""Teardown checklist (issue #37). See docs/teardown.md.

After the event: is everything back and is everything kept? Three parts check themselves:

- **Gear:** every piece checked out on the gear page (#36) is back.
- **Switch configs:** each placed switch is ticked once its config is archived (downloaded, or pushed
  to NetBox). Until switch configs can be read from the switches (#96), a person ticks it.
- **Event data:** the export (a backup of the floor plan and settings, the report as PDF, incidents,
  gear history and handovers in one zip) was downloaded.

Leads add their own steps too ("return the rented switches", "power down hall 2").
Kept in data.json under ``teardown``.
"""
import csv
import io
import json
import threading
import time
import uuid
import zipfile

from .store import load_data, save_data

KEY = 'teardown'
MAX_ITEMS = 100
MAX_TEXT = 200

_lock = threading.Lock()


class TeardownError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _stored(data):
    raw = data.get(KEY)
    raw = raw if isinstance(raw, dict) else {}
    return {'items': list(raw.get('items') or []), 'switches': dict(raw.get('switches') or {}),
            'export': raw.get('export')}


def _save(mutate):
    with _lock:
        data = load_data()
        state = _stored(data)
        result = mutate(data, state)
        data[KEY] = state
        save_data(data)
        return result


def status(data=None):
    from . import gear, inventory
    data = data if data is not None else load_data()
    state = _stored(data)
    out = gear.outstanding(data)
    placed = [d for d in inventory.devices(data) if d.get('role', 'switch') == 'switch' and d.get('x') is not None]
    switches = [{'id': d['id'], 'name': d.get('name') or '', 'archived': state['switches'].get(d['id'])}
                for d in sorted(placed, key=lambda d: str(d.get('name') or '').lower())]
    items = state['items']
    parts = {
        'gear': {'done': not out, 'left': len(out),
                 'out': [{'id': r['id'], 'name': r['name'], 'to': r['loan']['to'], 'at': r['loan']['at']}
                         for r in out]},
        'configs': {'done': all(s['archived'] for s in switches), 'left': sum(not s['archived'] for s in switches),
                    'switches': switches},
        'export': {'done': bool(state['export']), 'left': 0 if state['export'] else 1, 'last': state['export']},
        'custom': {'done': all(i.get('done_at') for i in items), 'left': sum(not i.get('done_at') for i in items),
                   'items': items},
    }
    total = len(out) + len(switches) + 1 + len(items)
    left = sum(p['left'] for p in parts.values())
    return {'parts': parts, 'done': left == 0, 'left': left, 'total': total}


def tick_switch(device_id, done, by, now=None):
    from . import inventory
    now = time.time() if now is None else now

    def change(data, state):
        if not inventory.find(data, device_id):
            raise TeardownError('No such switch.', 404)
        if done:
            state['switches'][device_id] = {'by': by, 'at': now}
        else:
            state['switches'].pop(device_id, None)
    _save(change)


def add_item(text, by, now=None):
    text = ' '.join(str(text or '').split())[:MAX_TEXT]
    if not text:
        raise TeardownError('Write what needs doing.')
    now = time.time() if now is None else now

    def change(data, state):
        if len(state['items']) >= MAX_ITEMS:
            raise TeardownError(f'At most {MAX_ITEMS} steps.')
        item = {'id': uuid.uuid4().hex[:10], 'text': text, 'added_by': by, 'added_at': now, 'done_by': None,
                'done_at': None}
        state['items'].append(item)
        return item
    return _save(change)


def tick_item(item_id, done, by, now=None):
    now = time.time() if now is None else now

    def change(data, state):
        item = next((i for i in state['items'] if i['id'] == item_id), None)
        if not item:
            raise TeardownError('No such step.', 404)
        item.update(done_by=by if done else None, done_at=now if done else None)
        return item
    return _save(change)


def remove_item(item_id):
    def change(data, state):
        before = len(state['items'])
        state['items'] = [i for i in state['items'] if i['id'] != item_id]
        if len(state['items']) == before:
            raise TeardownError('No such step.', 404)
    _save(change)


def mark_exported(by, now=None):
    now = time.time() if now is None else now

    def change(data, state):
        state['export'] = {'by': by, 'at': now}
    _save(change)


def _csv(rows, header):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for row in rows:
        w.writerow(["'" + v if isinstance(v, str) and v[:1] in ('=', '+', '-', '@') else v for v in row])
    return buf.getvalue()


def export_zip(backup, report_pdf, data=None):
    """Everything worth keeping from the event, without personal data beyond crew names."""
    from . import gear, handover, incidents
    data = data if data is not None else load_data()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('backup.json', json.dumps(backup, indent=2))
        z.writestr('report.pdf', report_pdf)
        z.writestr('incidents.csv', _csv(
            [(i['id'], i.get('title'), i.get('seat') or i.get('switch_name') or i.get('circuit_name') or '',
              i.get('team') or '', i.get('status'), i.get('assignee') or '', i.get('source'),
              _iso(i.get('created_at')), _iso(i.get('fixed_at'))) for i in incidents.list_all()],
            ('id', 'title', 'where', 'team', 'status', 'assignee', 'source', 'created', 'fixed')))
        z.writestr('gear-history.csv', _csv(
            [(e.get('name'), e.get('action'), e.get('to'), e.get('by') or '', _iso(e.get('at')), e.get('note') or '')
             for e in gear.log(data, limit=10_000)], ('gear', 'action', 'to', 'by', 'at', 'note')))
        z.writestr('handovers.json', json.dumps(handover.history(data), indent=2))
    return buf.getvalue()


def _iso(ts):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ts)) if ts else ''
