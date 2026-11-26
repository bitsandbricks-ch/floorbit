"""What discovery found that the inventory doesn't have yet (issues #891, #968): the Inventory's
Discovery tab. Nothing is added on its own; the crew adds or ignores each row.

- **Devices**: boxes the switches see by LLDP or CDP that match no inventory device, one row per
  name with every port that sees it.
- **Links**: links LLDP or CDP sees between two inventory devices that no planned link explains
  (``links.topology``'s suggestions). Until confirmed, the topology draws them dashed.

Unknown senders (#1443) are their own list (floorbit/unknown_senders.py); the tab shows them too.
Only switch and device names and port names: nothing here is personal data.
"""
from . import inventory, links

IGNORED = 'found_ignored'      # {"device": [name lower], "link": [key]}
MAX_IGNORED = 1000
MAX_ROWS = 500


def link_key(s):
    """One key for a link whichever end it is read from."""
    ends = sorted([f"{s['a']}|{s['a_port']}".lower(), f"{s['b']}|{s['b_port']}".lower()])
    return ' -- '.join(ends)


def ignored(data):
    value = data.get(IGNORED) if isinstance(data.get(IGNORED), dict) else {}
    return {k: [str(x) for x in value.get(k) or [] if isinstance(x, str)] for k in ('device', 'link')}


def set_ignored(data, kind, key, on=True):
    if kind not in ('device', 'link'):
        raise ValueError('kind is device or link')
    key = str(key or '').strip().lower()[:200]
    if not key:
        raise ValueError('Send the key')
    now = ignored(data)
    rows = [k for k in now[kind] if k != key]
    if on:
        rows.append(key)
    now[kind] = rows[-MAX_IGNORED:]
    data[IGNORED] = now
    return now


def collect(data, now=None):
    """{'devices': [...], 'links': [...], 'ignored': {'devices': n, 'links': n}}."""
    topo = links.topology(now=now, suggest=True)
    skip = ignored(data)
    known = set()
    for d in inventory.devices(data, include_hidden=True):
        for field in ('name', 'mgmt_ip'):
            if d.get(field):
                known.add(str(d[field]).lower())
                known.add(str(d[field]).lower().split('.')[0])
    devices = {}
    # topology() just read (or kept) every switch's neighbours; take them from its cache.
    for node in topo.get('nodes') or []:
        switch = node['name']
        for n in links.reader.cached_neighbours(switch):
            remote = str(n.get('remote') or '').strip()
            if not remote or remote.lower() in known or remote.lower().split('.')[0] in known:
                continue
            row = devices.setdefault(remote.lower(), {'name': remote[:64], 'seen_by': [], 'protocol': ''})
            row['protocol'] = row['protocol'] or str(n.get('protocol') or '')[:8]
            if len(row['seen_by']) < 20:
                row['seen_by'].append({'switch': switch, 'port': str(n.get('port') or '')[:48],
                                       'remote_port': str(n.get('remote_port') or '')[:48]})
    rows = [r for k, r in sorted(devices.items()) if k not in skip['device']]
    found_links = [{**s, 'key': link_key(s)} for s in topo.get('suggestions') or []]
    shown_links = [s for s in found_links if s['key'] not in skip['link']]
    return {'devices': rows[:MAX_ROWS], 'links': shown_links[:MAX_ROWS],
            'ignored': {'devices': len(devices) - len(rows), 'links': len(found_links) - len(shown_links)}}
