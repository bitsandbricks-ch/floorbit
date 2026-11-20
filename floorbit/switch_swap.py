"""Swap a dead switch for a spare (issue #1060).

A dead access switch is the worst minute of an event: a block offline, and the crew has to find a
spare, give it the old config, patch it in the same way, and fix every place that knows the old
hardware. Floorbit keeps the rest stable on purpose: the switch keeps its name and management IP,
and a seat's port is switch name + port, so the seat mapping, the cables, the monitoring and the
MAC history carry on by themselves. What changes is the hardware:

- **The spare** is an inventory switch with the status ``inventory`` (on the shelf), same model
  first. Or the crew types the new serial when the spare isn't in the inventory.
- **On "Swapped"** the switch takes the spare's serial and model, and the spare's entry takes the
  old ones with the status ``failed``: the dead box is now the one on the shelf, for the RMA, and
  nothing is deleted. Each swap is kept on the switch (``swaps``), audited, and noted on the
  switch's open incident.
- **The config** to paste is the switch's last backup (floorbit/config_backup.py); the page links it.
"""
import time

from . import config_backup, inventory

SPARE_STATUS = 'inventory'
GONE_STATUS = 'failed'
MAX_SWAPS = 20


class SwapError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _switch(data, device_id):
    dev = inventory.find(data, device_id)
    if dev is None or dev.get('role') not in ('switch', 'router'):
        raise SwapError('There is no such switch.', 404)
    return dev


def spares(data, dev):
    """Switches on the shelf, the same model first."""
    model = str(dev.get('model') or '').lower()
    out = [d for d in inventory.devices(data, include_hidden=True)
           if d['id'] != dev['id'] and d.get('role') == dev.get('role') and d.get('status') == SPARE_STATUS]
    out.sort(key=lambda d: (str(d.get('model') or '').lower() != model, str(d.get('name') or '').lower()))
    return [{'id': d['id'], 'name': d.get('name') or '', 'model': d.get('model') or '', 'serial': d.get('serial') or '',
             'same_model': bool(model) and str(d.get('model') or '').lower() == model} for d in out]


def _seat_ports(mapping, name):
    """The seats on this switch, by port: the new box is patched back exactly like this."""
    from .seatmap import _natural
    rows = [{'port': str(e.get('port') or ''), 'seat': str(seat)} for seat, e in (mapping or {}).items()
            if name and str((e or {}).get('switch') or '').lower() == name.lower() and (e or {}).get('port')]
    return sorted(rows, key=lambda r: (_natural(r['port']), _natural(r['seat'])))


def plan(data, device_id, status=None, can_read_configs=False, mapping=None):
    """What the swap page shows: the switch, whether it is down, the spares, the last config copy,
    the seat ports to patch back the same way and the switch's open incident."""
    from . import incidents
    dev = _switch(data, device_id)
    name = dev.get('name') or ''
    last = None
    if can_read_configs and name:
        copies = config_backup.history(name)['copies']
        last = {'id': copies[0]['id'], 'at': copies[0].get('at')} if copies else None
    incident = next((i for i in incidents.list_all()
                     if i.get('switch_id') == dev['id'] and i['status'] != 'fixed'), None)
    return {'switch': {'id': dev['id'], 'name': name, 'model': dev.get('model') or '',
                       'serial': dev.get('serial') or '', 'mgmt_ip': dev.get('mgmt_ip') or '',
                       'status': (status or {}).get('status') or 'unknown',
                       'since': (status or {}).get('since')},
            'spares': spares(data, dev), 'config': last, 'config_readable': can_read_configs,
            'seat_ports': _seat_ports(mapping, name),
            'incident': {'id': incident['id'], 'title': incident.get('title') or ''} if incident else None,
            'swaps': list(reversed(dev.get('swaps') or []))}


def swap(data, device_id, body, by, now=None):
    """Put the spare in the switch's place. ``body``: ``{spare_id}`` or ``{serial, model}``.
    Returns the swap as recorded. The caller saves ``data``."""
    now = time.time() if now is None else now
    dev = _switch(data, device_id)
    spare = None
    if body.get('spare_id'):
        spare = inventory.find(data, str(body['spare_id']))
        if spare is None or spare['id'] == dev['id'] or spare.get('status') != SPARE_STATUS:
            raise SwapError('That spare is not on the shelf any more.')
        new_serial, new_model = spare.get('serial') or '', spare.get('model') or dev.get('model') or ''
    else:
        new_serial = inventory.clean_field('serial', body.get('serial'))
        new_model = inventory.clean_field('model', body.get('model')) or dev.get('model') or ''
    if not new_serial:
        raise SwapError('Pick a spare or type the new switch\'s serial number.')
    old_serial, old_model = dev.get('serial') or '', dev.get('model') or ''
    if new_serial == old_serial:
        raise SwapError('That is the serial number the switch already has.')
    inventory.update(data, dev['id'], {'serial': new_serial, 'model': new_model})
    if spare is not None:
        # The dead box goes on the shelf in the spare's place: kept for the RMA, never deleted.
        note = f"Pulled from {dev.get('name')} on {time.strftime('%d.%m.%Y %H:%M', time.localtime(now))}."
        notes = ' '.join(x for x in (spare.get('notes') or '', note) if x)[-inventory.LIMITS['notes']:]
        inventory.update(data, spare['id'], {'serial': old_serial, 'model': old_model, 'status': GONE_STATUS,
                                             'notes': notes})
    entry = {'at': now, 'by': by or '', 'old_serial': old_serial, 'old_model': old_model,
             'new_serial': new_serial, 'new_model': new_model, 'spare_id': spare['id'] if spare else None}
    dev['swaps'] = ([*(dev.get('swaps') or []), entry])[-MAX_SWAPS:]
    return entry
