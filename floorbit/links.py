"""Links between switches (issue #468): uplinks with their cable type and speed, and the topology.

- **A link** is ``switch port <-> switch port`` with a type (copper Cat5e/6/6a, fiber single-mode or
  multi-mode, DAC) and a planned speed (1, 10, 25, 40 or 100G). Kept in data.json under ``links``;
  the crew adds and changes them (``floorplan.edit``).
- **Live**: each link's ports as the monitoring source reads them (``device_ports``): down, or up
  slower than planned (a 10G uplink that came up at 1G is a wrong optic or cable).
- **Suggestions**: what the switches see by LLDP or CDP (the source's optional ``neighbours``) that
  no link explains yet, to add with one click. The plan stays the crew's.

Switch names only: nothing here is personal data.
"""
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import inventory, sources
from .store import load_data, save_data

KEY = 'links'
MAX_LINKS = 2000
TYPES = ('cat5e', 'cat6', 'cat6a', 'fiber-sm', 'fiber-mm', 'dac')
MEDIA = {'cat5e': 'copper', 'cat6': 'copper', 'cat6a': 'copper', 'fiber-sm': 'fiber', 'fiber-mm': 'fiber',
         'dac': 'dac'}
SPEEDS = (1, 10, 25, 40, 100)           # Gbit/s
PORT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/._:-]{0,47}$')
ROLES = ('switch', 'router', 'firewall')  # what the topology draws
READ_EVERY = 30                          # seconds a switch's ports are kept
NEIGHBOURS_EVERY = 120
_lock = threading.Lock()


class LinkError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _canon(port):
    from .syslog import canonical_port  # syslog imports the seat data: late
    return canonical_port(port)


def all_links(data=None):
    data = load_data() if data is None else data
    return [link for link in data.get(KEY) or [] if isinstance(link, dict) and link.get('id')]


def _switch_names(data):
    return {str(d['name']).lower(): d['name'] for d in inventory.devices(data, include_hidden=True) if d.get('name')}


def _clean(body, data, current=None):
    current = current or {}
    names = _switch_names(data)
    out = {}
    for end in ('a', 'b'):
        switch = str(body.get(end, current.get(end)) or '').strip()
        if switch.lower() not in names:
            raise LinkError('Pick both switches from the inventory.')
        port = str(body.get(f'{end}_port', current.get(f'{end}_port')) or '').strip()
        if not PORT_RE.match(port):
            raise LinkError('Name the port at both ends, like Te1/1/1.')
        out[end], out[f'{end}_port'] = names[switch.lower()], port
    if out['a'] == out['b']:
        raise LinkError('A link joins two different switches.')
    kind = body.get('type', current.get('type')) or ''
    if kind and kind not in TYPES:
        raise LinkError('The type is cat5e, cat6, cat6a, fiber-sm, fiber-mm or dac.')
    speed = body.get('speed', current.get('speed'))
    if speed in ('', None):
        speed = None
    else:
        try:
            speed = int(speed)
        except (TypeError, ValueError):
            speed = 0
        if speed not in SPEEDS:
            raise LinkError('The speed is 1, 10, 25, 40 or 100 (Gbit/s).')
    out.update(type=kind, speed=speed, note=' '.join(str(body.get('note', current.get('note')) or '').split())[:200])
    return out


def _ends(link):
    return {(link['a'].lower(), _canon(link['a_port'])), (link['b'].lower(), _canon(link['b_port']))}


def save(body, by, link_id=None):
    with _lock:
        data = load_data()
        rows = data.setdefault(KEY, [])
        link = next((x for x in rows if x.get('id') == link_id), None) if link_id else None
        if link_id and link is None:
            raise LinkError('No such link.', 404)
        fields = _clean(body, data, link)
        mine = _ends(fields)
        clash = next((x for x in rows if x is not link and _ends(x) & mine), None)
        if clash:
            raise LinkError(f"The link from {clash['a']} {clash['a_port']} to {clash['b']} {clash['b_port']} "
                            'already uses one of these ports.', 409)
        if link is None:
            if len(rows) >= MAX_LINKS:
                raise LinkError(f'Floorbit keeps at most {MAX_LINKS} links.')
            link = {'id': uuid.uuid4().hex[:12]}
            rows.append(link)
        link.update(fields, updated_at=time.time(), by=by)
        save_data(data)
    return dict(link)


def delete(link_id):
    with _lock:
        data = load_data()
        rows = data.get(KEY) or []
        gone = next((x for x in rows if x.get('id') == link_id), None)
        if gone is None:
            return None
        data[KEY] = [x for x in rows if x is not gone]
        save_data(data)
    return gone


# ── live ────────────────────────────────────────────────────────────────────
class Reader:
    """Ports and neighbours per switch, kept a little while: the topology page polls."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ports = {}           # switch lower -> (at, {canonical port: port} or None when unreadable)
        self._neighbours = {}      # switch lower -> (at, [...])

    def reset(self):
        with self._lock:
            self._ports.clear()
            self._neighbours.clear()

    def _kept(self, store, key, every, now):
        with self._lock:
            hit = store.get(key)
            return hit[1] if hit and now - hit[0] < every else False

    def ports(self, switch, now):
        hit = self._kept(self._ports, switch.lower(), READ_EVERY, now)
        if hit is not False:
            return hit
        try:
            ports = {_canon(p['name']): p for p in sources.monitoring().device_ports(switch) or [] if p.get('name')}
        except Exception:  # noqa: BLE001 - a switch that can't be read is "unknown", not an error page
            ports = None
        with self._lock:
            self._ports[switch.lower()] = (now, ports)
        return ports

    def neighbours(self, switch, now):
        hit = self._kept(self._neighbours, switch.lower(), NEIGHBOURS_EVERY, now)
        if hit is not False:
            return hit
        try:
            rows = sources.monitoring().neighbours(switch) or []
        except Exception:  # noqa: BLE001
            rows = []
        with self._lock:
            self._neighbours[switch.lower()] = (now, rows)
        return rows


reader = Reader()


def _live(link, ports):
    """How the link is now: its state and speed as one of its ends reports them."""
    for end in ('a', 'b'):
        read = ports.get(link[end].lower())
        port = (read or {}).get(_canon(link[f'{end}_port'])) if read is not None else None
        if port is None:
            continue
        speed = port.get('speed_bps')
        state = port.get('state') if port.get('state') in ('up', 'down') else 'unknown'
        issue = ''
        if state == 'down':
            issue = 'down'
        elif state == 'up' and link.get('speed') and isinstance(speed, (int, float)) \
                and 0 < speed < link['speed'] * 1e9:
            issue = 'slow'
        return {'state': state, 'speed_bps': speed if isinstance(speed, (int, float)) else None, 'issue': issue,
                'read_at': end}
    return {'state': 'unknown', 'speed_bps': None, 'issue': '', 'read_at': None}


def topology(now=None, suggest=True):
    """The switches, the links with how they are now, and what LLDP sees that no link explains."""
    now = time.time() if now is None else now
    data = load_data()
    devices = [d for d in inventory.devices(data) if d.get('role') in ROLES and d.get('name')]
    links = all_links(data)
    names = {str(d['name']).lower(): d['name'] for d in devices}
    wanted = sorted({link[e] for link in links for e in ('a', 'b')} | (set(names.values()) if suggest else set()))
    with ThreadPoolExecutor(8) as pool:
        ports = dict(zip([w.lower() for w in wanted], pool.map(lambda s: reader.ports(s, now), wanted), strict=True))
        seen = dict(zip(names, pool.map(lambda s: reader.neighbours(s, now), names.values()), strict=True)) \
            if suggest else {}
    rows = [{**link, 'media': MEDIA.get(link.get('type') or '', ''), **_live(link, ports)} for link in links]
    used = set().union(*(_ends(link) for link in links)) if links else set()
    suggestions, pairs = [], set()
    for switch, found in seen.items():
        for n in found:
            remote = str(n.get('remote') or '').lower()
            other = names.get(remote) or names.get(remote.split('.')[0])
            if not other or not n.get('port') or not n.get('remote_port'):
                continue
            a, b = (names[switch], n['port']), (other, n['remote_port'])
            ends = {(a[0].lower(), _canon(a[1])), (b[0].lower(), _canon(b[1]))}
            key = frozenset(ends)
            if ends & used or key in pairs:
                continue
            pairs.add(key)
            port = (ports.get(switch) or {}).get(_canon(a[1])) or {}
            speed = port.get('speed_bps')
            guess = next((s for s in SPEEDS if isinstance(speed, (int, float)) and speed == s * 1e9), None)
            suggestions.append({'a': a[0], 'a_port': a[1], 'b': b[0], 'b_port': b[1],
                                'protocol': str(n.get('protocol') or '')[:8], 'speed': guess})
    nodes = [{'id': d['id'], 'name': d['name'], 'role': d.get('role'), 'hall': d.get('hall') or '',
              'unread': ports.get(str(d['name']).lower()) is None} for d in devices]
    return {'nodes': sorted(nodes, key=lambda n: n['name'].lower()), 'links': rows,
            'suggestions': sorted(suggestions, key=lambda s: (s['a'].lower(), s['a_port'])),
            'counts': {'links': len(rows), 'down': sum(r['issue'] == 'down' for r in rows),
                       'slow': sum(r['issue'] == 'slow' for r in rows)},
            'types': list(TYPES), 'speeds': list(SPEEDS)}
