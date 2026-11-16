"""The patch plan checked against the network (issue #473): do the ports the cables say are a seat's
come up, and what is up that no cable explains?

It reads only what the port watch (attention.py) read on its last poll, so it costs no extra
LibreNMS calls however many seats there are.
"""
from . import cables as cables_mod
from .store import load_data

MAX_LISTED = 200     # per list: past that the count says it


def _listed(rows):
    return {'count': len(rows), 'rows': rows[:MAX_LISTED]}


def check(port_reads, read_switches, data=None):
    """``{"blocks": [...], "missing", "down", "unplanned", "conflicts", "unread"}``.

    - ``missing``: a cable names a port the switch doesn't have (a typo, or the wrong switch).
    - ``down``: the seat's port is there and not up (fine before doors, a problem during the event).
    - ``unplanned``: a port is up on a switch with seats, and no cable says what is on it.
    - ``conflicts``: the port's description names another seat than the cable does.
    - ``unread``: cabled switches the port watch didn't read (not on the floor plan, or offline).
    """
    from .syslog import canonical_port  # syslog reads attention, which reads this: late
    data = load_data() if data is None else data
    all_cables = cables_mod.all_cables(data)
    names = {b.get('id'): b.get('name') or '' for b in data.get('seat_blocks') or []}
    blocks, missing, down, conflicts, unread = {}, [], [], [], set()
    cabled = set()
    seat_switches = set()
    for c in all_cables:
        key = (c['switch'].lower(), canonical_port(c['port']))
        cabled.add(key)
        if not c.get('seat'):
            continue
        seat_switches.add(key[0])
        block_id = c.get('block') or ''
        block = blocks.setdefault(block_id, {'block': block_id, 'name': names.get(block_id, ''), 'seats': 0, 'up': 0})
        block['seats'] += 1
        row = {'seat': c['seat'], 'switch': c['switch'], 'port': c['port'], 'cable': c['label']}
        if key[0] not in read_switches:
            unread.add(c['switch'])
            continue
        read = port_reads.get(key)
        if read is None:
            missing.append(row)
        elif read.get('state') in ('up', 'errors'):
            block['up'] += 1
        else:
            down.append({**row, 'state': read.get('state') or 'unknown'})
        if read and read.get('described_seat') and read['described_seat'] != c['seat']:
            conflicts.append({**row, 'described_seat': read['described_seat']})
    unplanned = sorted(
        ({'switch': r['switch'], 'port': r['port'], 'described_seat': r.get('described_seat') or ''}
         for key, r in port_reads.items()
         if key[0] in seat_switches and key not in cabled and r.get('state') in ('up', 'errors')),
        key=lambda r: (r['switch'].lower(), canonical_port(r['port'])))
    ordered = sorted(blocks.values(), key=lambda b: (b['block'] == '', b['name'].lower()))
    return {'blocks': ordered, 'missing': _listed(missing), 'down': _listed(down),
            'unplanned': _listed(unplanned), 'conflicts': _listed(conflicts), 'unread': sorted(unread)}
