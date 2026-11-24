"""Firewalls and the ranges they serve (issue #470).

The core policy-routes each seat range to its firewalls, and (only where it is set up to) to a
fallback while one is down. Floorbit keeps that plan and shows it against the firewalls' health:

- **The firewalls** are the inventory's devices with the role ``firewall``.
- **A range** is a network (``192.0.2.0/24``) or any span of addresses (``192.0.2.0-192.0.2.128``:
  the core policy-routes by address, not by CIDR block, issue #866) with the firewalls it routes to.
  With several, the range is cut into equal **parts**, one per firewall in their order: a /24 over
  four firewalls sends each quarter to its own (Mike, 2026-11-24). ``fallback``, optional, lists
  where a part goes while its own firewall is down; most events have none.
  A range is an inventory **prefix** with firewalls set (Mike, 2026-11-24, issue #1345): the plan
  is kept on the prefix entry (``plan``, floorbit/inventory_types.py), so a network is written down
  once. The crew plans it (``floorplan.edit``), or imports it from NetBox prefixes that have the
  custom field ``floorbit_firewalls`` (``source: import``; each import replaces the last).
- **Now**: a part's firewall, or the first fallback, that the monitoring source doesn't report down.
  A firewall the source can't tell about counts as up (the core would still route to it), but the
  part says so (``unknown``).

A seat's range is the most specific one its IP is in, and within it the part its IP is in. Seat IPs
never leave this module: the seat panel gets the firewall names only.
"""
import ipaddress
import threading
import time
import uuid

from integrations import seat_sources
from integrations.monitor import StatusMonitor

from . import inventory, sources
from .store import load_data, save_data

TYPE = 'prefix'           # the inventory type a range lives on (inventory_types.BUILTIN)
MAX_RANGES = 500
MAX_LINE = 16            # firewalls one range is cut over (and in its fallback)
READ_EVERY = 15          # seconds the source's device list is kept
_lock = threading.Lock()


class FirewallError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _prefixes(data):
    from . import inventory_types
    return [e for e in inventory_types._entries(data) if e['type'] == TYPE]


def _plan(entry):
    plan = entry.get('plan')
    return plan if isinstance(plan, dict) and plan.get('firewalls') else None


def _cidr_of(entry):
    try:
        return str(_parse((entry.get('fields') or {}).get('prefix')))
    except ValueError:
        return None


def _row(entry, cidr):
    """A planned prefix as a range: what the rest of this module (and the API) works with."""
    plan, name = entry.get('plan') or {}, entry.get('name') or ''
    return {'id': entry['id'], 'cidr': cidr, 'name': '' if name == cidr else name,
            'firewalls': list(plan.get('firewalls') or []), 'fallback': list(plan.get('fallback') or []),
            'switches': list(plan.get('switches') or []), 'source': plan.get('source') or 'floorbit',
            'plugin': plan.get('plugin') or '', 'updated_at': plan.get('updated_at'), 'by': plan.get('by')}


def _ranges(data):
    out = []
    for entry in _prefixes(data):
        cidr = _cidr_of(entry) if _plan(entry) else None
        if cidr:
            out.append(_row(entry, cidr))
    return out


def _holder(entries, cidr):
    """The prefix entry for ``cidr`` that a plan goes on: one planned already, else one a source
    keeps (NetBox, discovery), else any."""
    same = [e for e in entries if _cidr_of(e) == cidr]
    return next((e for e in same if _plan(e)), None) or next((e for e in same if e.get('refs')), None) or \
        (same[0] if same else None)


def _new_entry(data, name, cidr, entry_id=None):
    from . import inventory_types
    entries = inventory_types._entries(data)
    if len(entries) >= inventory_types.MAX_ENTRIES:
        raise FirewallError(f'The inventory holds at most {inventory_types.MAX_ENTRIES} entries.', 409)
    taken = {e['id'] for e in entries}
    entry = {'id': entry_id if entry_id and entry_id not in taken else uuid.uuid4().hex[:12], 'type': TYPE,
             'name': name, 'fields': {'prefix': cidr},
             # Made for the plan: it goes when the plan goes, unless a source keeps it.
             'made_for': 'firewalls'}
    data[inventory_types.ENTRIES] = [*entries, entry]
    return entry


def _name_taken(data, entry, name):
    return any(e is not entry and (e.get('name') or '').lower() == name.lower() for e in _prefixes(data))


def _by_hand(entry, key, value):
    """Sets a name or field on a prefix; one a source keeps stays as set from now on (inventory sync)."""
    current = (entry.get('fields') or {}).get(key[7:]) if key.startswith('fields.') else entry.get(key)
    if current == value:
        return
    if key.startswith('fields.'):
        entry.setdefault('fields', {})[key[7:]] = value
    else:
        entry[key] = value
    if entry.get('refs'):
        locked = entry.setdefault('locked', [])
        if key not in locked:
            locked.append(key)


def _drop(data, entry):
    """Takes the plan off a prefix; one made only for it goes too."""
    from . import inventory_types
    entry.pop('plan', None)
    if entry.get('made_for') == 'firewalls' and not entry.get('refs'):
        data[inventory_types.ENTRIES] = [e for e in inventory_types._entries(data) if e is not entry]


def adopt(data, rows):
    """Ranges in the shape Floorbit kept them before issue #1345 (``data['firewalls']['ranges']``)
    onto prefix entries, as they are: for the upgrade step and the demo. Returns {old id: entry id}."""
    moved = {}
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        try:
            cidr = str(_parse(raw.get('cidr')))
        except ValueError:
            continue
        entries = _prefixes(data)
        entry = _holder(entries, cidr)
        if entry is not None and _plan(entry):
            continue
        if entry is None:
            name = ' '.join(str(raw.get('name') or '').split())[:80] or cidr
            if any((e.get('name') or '').lower() == name.lower() for e in entries):
                name = cidr if name != cidr else f'{cidr} ({len(entries) + 1})'
            entry = _new_entry(data, name, cidr, str(raw.get('id') or '') or None)
        entry['plan'] = {'firewalls': [str(n) for n in raw.get('firewalls') or []],
                         'fallback': [str(n) for n in raw.get('fallback') or []],
                         'switches': [str(n) for n in raw.get('switches') or []],
                         'source': 'import' if raw.get('source') == 'import' else 'floorbit',
                         'plugin': str(raw.get('plugin') or ''), 'updated_at': raw.get('updated_at'),
                         'by': raw.get('by')}
        if raw.get('id'):
            moved[str(raw['id'])] = entry['id']
    return moved


def _firewall_names(data):
    return {str(d['name']).lower(): d['name'] for d in inventory.devices(data, include_hidden=True)
            if d.get('role') == 'firewall' and d.get('name')}


class Span:
    """Addresses from ``first`` to ``last``: a network or any range the core routes by policy."""

    def __init__(self, first, last):
        self.first, self.last = first, last
        self.version = first.version

    def __contains__(self, ip):
        return ip.version == self.version and self.first <= ip <= self.last

    @property
    def size(self):
        return int(self.last) - int(self.first) + 1

    def overlaps(self, other):
        return self.version == other.version and self.first <= other.last and other.first <= self.last

    def __str__(self):
        # A span that is exactly one network is written as one, so imports and splits still compare.
        nets = list(ipaddress.summarize_address_range(self.first, self.last))
        return str(nets[0]) if len(nets) == 1 else f'{self.first}-{self.last}'

    def sort_key(self):
        return (self.version, int(self.first), -self.size)


def _parse(value):
    text = str(value or '').strip()
    if '-' in text:
        a, b = (part.strip() for part in text.split('-', 1))
        first, last = ipaddress.ip_address(a), ipaddress.ip_address(b)
        if '.' not in b and ':' not in b:
            raise ValueError(text)
        if first.version != last.version or first > last:
            raise ValueError(text)
        return Span(first, last)
    net = ipaddress.ip_network(text, strict=False)
    return Span(net.network_address, net.broadcast_address)


def parts(span, firewalls):
    """[(Span, firewall)]: ``span`` cut into one equal part per firewall, in their order. Addresses
    that don't divide evenly go one each to the first parts."""
    if not firewalls:
        return []
    count = min(len(firewalls), span.size)
    each, extra = divmod(span.size, count)
    out, start = [], int(span.first)
    cls = type(span.first)
    for i in range(count):
        end = start + each + (1 if i < extra else 0) - 1
        out.append((Span(cls(start), cls(end)), firewalls[i]))
        start = end + 1
    return out


def _network(value):
    try:
        return _parse(value)
    except ValueError:
        raise FirewallError('Write the range as a network (192.0.2.0/27) or from-to '
                            '(192.0.2.0-192.0.2.128).') from None


def _clean(body, data, current=None):
    current = current or {}
    net = _network(body.get('cidr', current.get('cidr')))
    names = _firewall_names(data)
    line = body.get('firewalls', current.get('firewalls'))
    if not isinstance(line, list) or not line:
        raise FirewallError('Pick at least one firewall for the range.')
    out = _pick(line, names)
    if len(out) > net.size:
        raise FirewallError(f'{net} has fewer addresses than firewalls to share it.')
    fallback = body.get('fallback', current.get('fallback') or [])
    if not isinstance(fallback, list):
        raise FirewallError('Send the fallback firewalls as a list.')
    fallback = [n for n in _pick(fallback, names) if n not in out] if fallback else []
    label = ' '.join(str(body.get('name', current.get('name')) or '').split())[:60]
    return {'cidr': str(net), 'name': label, 'firewalls': out, 'fallback': fallback,
            'switches': _switches(body, data, current)}


def _pick(line, names):
    out = []
    for name in line:
        found = names.get(str(name or '').strip().lower())
        if not found:
            raise FirewallError('Pick the firewalls from the inventory (devices with the role firewall).')
        if found not in out:
            out.append(found)
    if len(out) > MAX_LINE:
        raise FirewallError(f'A range has at most {MAX_LINE} firewalls.')
    return out


def _switches(body, data, current):
    """The switches or switch groups a range is for (optional, issue #1062): inventory device or
    group ids. A seat behind one of them with an address outside their ranges is flagged
    (floorbit/seat_ranges.py). Without any, each switch's range is guessed from its seats."""
    from . import inventory, inventory_scope
    raw = body.get('switches', current.get('switches') or [])
    if not isinstance(raw, list):
        raise FirewallError('Send the switches as a list.')
    known = {d['id'] for d in inventory.devices(data)} | {g['id'] for g in inventory_scope.groups(data)}
    out = []
    for item in raw:
        item = str(item or '')
        if item not in known:
            raise FirewallError('Pick the switches and groups from the inventory.')
        if item not in out:
            out.append(item)
    return out


def save(body, by, range_id=None):
    """Plans a range, or changes one (``range_id``: its prefix entry). A network the inventory has
    already gets the plan on its prefix; otherwise a prefix is made for it."""
    with _lock:
        data = load_data()
        entry = next((e for e in _prefixes(data) if e['id'] == range_id), None) if range_id else None
        if range_id and (entry is None or not _plan(entry)):
            raise FirewallError('No such range.', 404)
        row = _row(entry, _cidr_of(entry) or '') if entry else None
        if row is not None and row['source'] == 'import' and set(body) == {'switches'}:
            # Which switches a range is for is Floorbit's own: kept on an imported range too.
            entry['plan']['switches'] = _switches(body, data, row)
            save_data(data)
            return _row(entry, row['cidr'])
        if row is not None and row['source'] == 'import':
            raise FirewallError(f"This range comes from {row['plugin'] or 'NetBox'}: change it there and import "
                                'again.', 409)
        fields = _clean(body, data, row)
        cidr = fields['cidr']
        others = [r for r in _ranges(data) if entry is None or r['id'] != entry['id']]
        if any(r['cidr'] == cidr for r in others):
            raise FirewallError(f'{cidr} is planned already.', 409)
        clash = _partly_over(_parse(cidr), others)
        if clash:
            raise FirewallError(f"{cidr} overlaps {clash} only in part: make one range inside the other, "
                                'or split them where they meet.', 409)
        if entry is None and len(others) >= MAX_RANGES:
            raise FirewallError(f'Floorbit keeps at most {MAX_RANGES} ranges.')
        made = False
        if entry is None:
            entry = _holder([e for e in _prefixes(data) if not _plan(e)], cidr)
        if entry is None:
            entry, made = _new_entry(data, fields['name'] or cidr, cidr), True
        name = fields['name'] or (cidr if made or (row is not None and 'name' in body) else entry.get('name'))
        if _name_taken(data, entry, name):
            raise FirewallError(f'There is a prefix called {name} already.', 409)
        _by_hand(entry, 'name', name)
        _by_hand(entry, 'fields.prefix', cidr)
        entry['plan'] = {'firewalls': fields['firewalls'], 'fallback': fields['fallback'],
                         'switches': fields['switches'], 'source': 'floorbit', 'plugin': '',
                         'updated_at': time.time(), 'by': by}
        save_data(data)
        return _row(entry, cidr)


def _partly_over(span, rows):
    """The first range that overlaps ``span`` without one holding the other. Nested ranges are fine
    (the narrower one wins); two that only cross would leave the addresses between them ambiguous."""
    for r in rows:
        try:
            other = _parse(r.get('cidr'))
        except ValueError:
            continue
        inside = (other.first <= span.first and span.last <= other.last) or \
                 (span.first <= other.first and other.last <= span.last)
        if span.overlaps(other) and not inside:
            return r.get('cidr')
    return None


# ── import from NetBox ───────────────────────────────────────────────────────
FIELD = 'floorbit_firewalls'   # the NetBox custom field on a prefix: its firewalls, in order


def import_sources(registry):
    """Inventory plugins that can list firewall ranges (NetBox)."""
    if registry is None:
        return []
    return [spec for spec in registry.feeders('inventory')
            if (cls := spec.plugin_class()) is not None and hasattr(cls, 'firewall_ranges')]


def can_import():
    from . import agent_link
    return agent_link.active() or bool(import_sources(sources.registry))


def import_from(registry, by):
    """Replace the ranges read from plugins with what they list now; the crew's own ranges stay, and
    a network the crew planned already keeps the crew's line. Returns (added, errors)."""
    from . import agent_link
    from .plugins.base import PluginError
    found, errors, answered = [], [], set()
    if agent_link.active():
        # A hosted Floorbit: the local agent asks the event's NetBox.
        try:
            feeds = agent_link.feeds('firewall_feeds')
        except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
            feeds = []
            errors.append(f'Local agent: {exc}')
        for feed in feeds:
            if 'error' in feed:
                errors.append(f"{feed['name']} (local agent): {feed['error']}")
            else:
                found += [(feed['name'], r) for r in feed['items']]
                answered.update({feed['name'], feed.get('base_name', feed['name'])})
    for spec in import_sources(registry):
        if spec.name in answered or not agent_link.may_call_here(spec):
            continue
        try:
            found += [(spec.name, r) for r in registry.call(spec, 'firewall_ranges') or []]
            answered.add(spec.name)
        except PluginError as exc:
            errors.append(f'{spec.name}: {exc}')
    if errors and not answered:
        raise FirewallError('; '.join(errors), 502)
    with _lock:
        data = load_data()
        rows = _ranges(data)
        # The crew's own ranges stay; a network the crew planned keeps the crew's line.
        crew = {r['cidr'] for r in rows if r['source'] != 'import' or r['plugin'] not in answered}
        count = len(crew)
        seen, added, unknown, clash = set(), 0, 0, 0
        for plugin, raw in found:
            if not isinstance(raw, dict):
                continue
            try:
                fields = _clean({'cidr': raw.get('cidr'), 'name': raw.get('name'), 'firewalls': raw.get('firewalls'),
                                 'switches': []}, data)
            except FirewallError:
                unknown += 1   # one prefix with a typo in NetBox must not stop the rest
                continue
            cidr = fields['cidr']
            if cidr in crew:
                clash += 1
                continue
            if cidr in seen:
                continue
            if count + len(seen) >= MAX_RANGES:
                break
            seen.add(cidr)
            entry = _holder(_prefixes(data), cidr)
            if entry is None:
                name = fields['name'] or cidr
                entry = _new_entry(data, cidr if _name_taken(data, None, name) else name, cidr)
            # The switches set on an imported range survive the next import (NetBox doesn't know them).
            before = (entry.get('plan') or {}).get('switches') or []
            entry['plan'] = {'firewalls': fields['firewalls'], 'fallback': [], 'switches': list(before),
                             'source': 'import', 'plugin': plugin, 'updated_at': time.time(), 'by': by}
            added += 1
        # What a source that answered no longer lists goes; one that failed keeps its last import.
        for entry in _prefixes(data):
            plan = _plan(entry)
            if plan and plan.get('source') == 'import' and plan.get('plugin') in answered \
                    and _cidr_of(entry) not in seen:
                _drop(data, entry)
        save_data(data)
    if unknown:
        errors.append(f'{unknown} prefix(es) skipped: not a network, or a firewall that is not in the inventory.')
    if clash:
        errors.append(f'{clash} prefix(es) skipped: planned in Floorbit already.')
    return added, errors


def delete(range_id):
    """Takes a range's plan off its prefix (the prefix stays where a source or the crew keeps it)."""
    with _lock:
        data = load_data()
        entry = next((e for e in _prefixes(data) if e['id'] == range_id and _plan(e)), None)
        if entry is None:
            return None
        gone = _row(entry, _cidr_of(entry) or '')
        _drop(data, entry)
        save_data(data)
    return gone


# ── health ──────────────────────────────────────────────────────────────────
class Health:
    """The source's device list, kept a few seconds: the seat panel asks on every click."""

    def __init__(self):
        self._lock = threading.Lock()
        self._at = None
        self._devices = None      # None: the source couldn't be read

    def reset(self):
        with self._lock:
            self._at, self._devices = None, None

    def devices(self, now):
        with self._lock:
            if self._at is not None and 0 <= now - self._at < READ_EVERY:
                return self._devices
        if StatusMonitor.latest['polled'] is not None:
            # The status monitor is polling: use its list rather than ask a source that may be
            # hanging (the page waited for its timeout). None, "unknown", when its last poll failed.
            latest = StatusMonitor.latest
            found = latest['devices'] if latest['at'] is not None and latest['at'] >= latest['polled'] else None
            with self._lock:
                self._at, self._devices = now, found
            return found
        try:
            source = sources.monitoring()
            found = source.devices() if source.enabled() else None
        except Exception:  # noqa: BLE001 - an unreadable source means "unknown", not an error page
            found = None
        with self._lock:
            self._at, self._devices = now, found
        return found

    def status(self, name, now):
        """online, offline or unknown, the way the status monitor reads it."""
        found = self.devices(now)
        if found is None:
            return 'unknown'
        return StatusMonitor.device_status(StatusMonitor.match(name, found))


health = Health()
# A range's state is its worst part's.
STATES = ('down', 'failover', 'unknown', 'primary')


def _route(line, status):
    """(firewall now, state) for one part: its firewall first, then the fallback. primary,
    failover, unknown or down."""
    for i, name in enumerate(line):
        if status[name] == 'offline':
            continue
        if status[name] == 'unknown':
            return name, 'unknown'
        return name, 'primary' if i == 0 else 'failover'
    return None, 'down'


def _seat_ips():
    out = {}
    for seat, entry in (seat_sources.load() or {}).items():
        try:
            out[str(seat).upper()] = ipaddress.ip_address(str((entry or {}).get('ip_address') or '').strip())
        except ValueError:
            continue
    return out


def _match(ip, nets):
    """The narrowest range ``ip`` is in, like the core's routing table."""
    best = None
    for row, net in nets:
        if ip in net and (best is None or net.size < best[1].size):
            best = (row, net)
    return best[0] if best else None


def _parts(data):
    """[(range row, part span, its firewall)] for every range: what the core routes by."""
    out = []
    for row, span in _nets(data):
        out += [(row, part, fw) for part, fw in parts(span, list(row.get('firewalls') or []))]
    return out


def _part_of(ip, rows):
    """(row, part span, firewall) for ``ip``: the narrowest range it is in, then its part there."""
    row = _match(ip, [(r, span) for r, span, _fw in rows])
    if row is None:
        return None
    return next(((r, span, fw) for r, span, fw in rows if r['id'] == row['id'] and ip in span), None)


def _nets(data):
    out = []
    for row in _ranges(data):
        try:
            out.append((row, _parse(row['cidr'])))
        except ValueError:
            continue
    return out


def overview(now=None):
    """The firewalls with their health and what they serve, and every range with its route now."""
    now = time.time() if now is None else now
    data = load_data()
    firewalls = [d for d in inventory.devices(data) if d.get('role') == 'firewall' and d.get('name')]
    rows = _ranges(data)
    names = {d['name'] for d in firewalls} | {n for r in rows for n in
                                              [*(r.get('firewalls') or []), *(r.get('fallback') or [])]}
    status = {n: health.status(n, now) for n in names}
    every = _parts(data)
    seats = {}
    for _seat, ip in _seat_ips().items():
        found = _part_of(ip, every)
        if found:
            key = (found[0]['id'], str(found[1]))
            seats[key] = seats.get(key, 0) + 1
    ranges, all_parts = [], []
    for row in rows:
        fallback = [n for n in row.get('fallback') or [] if n in status]
        shown = []
        for part, fw in ((p, f) for r, p, f in every if r['id'] == row['id']):
            now_on, state = _route([fw, *fallback], status)
            shown.append({'cidr': str(part), 'firewall': fw, 'now': now_on, 'state': state,
                          'seats': seats.get((row['id'], str(part)), 0)})
        all_parts += shown
        worst = min((p['state'] for p in shown), key=STATES.index, default='down')
        ranges.append({'id': row['id'], 'cidr': row['cidr'], 'name': row.get('name') or '',
                       'firewalls': list(row.get('firewalls') or []), 'fallback': fallback, 'parts': shown,
                       'state': worst, 'seats': sum(p['seats'] for p in shown),
                       'source': row.get('source') or 'floorbit', 'switches': list(row.get('switches') or []),
                       'plugin': row.get('plugin') or ''})
    ranges.sort(key=lambda r: _parse(r['cidr']).sort_key())
    cards = []
    for d in firewalls:
        name = d['name']
        cards.append({'id': d['id'], 'name': name, 'model': d.get('model') or '', 'hall': d.get('hall') or '',
                      'status': status.get(name, 'unknown'),
                      'serving': [p['cidr'] for p in all_parts if p['now'] == name],
                      'planned': [p['cidr'] for p in all_parts if p['firewall'] == name],
                      # Parts that fell back to it from their own firewall, not a standing "backup" role.
                      'taken_over': [p['cidr'] for p in all_parts if p['now'] == name and p['firewall'] != name],
                      'seats': sum(p['seats'] for p in all_parts if p['now'] == name)})
    cards.sort(key=lambda c: c['name'].lower())
    return {'firewalls': cards, 'ranges': ranges,
            'counts': {'firewalls': len(cards), 'down': sum(c['status'] == 'offline' for c in cards),
                       'failover': sum(p['state'] == 'failover' for p in all_parts),
                       'without': sum(p['state'] == 'down' for p in all_parts)},
            'monitoring': _monitored(),
            'unread': _monitored() and health.devices(now) is None, 'can_import': can_import()}


def _monitored():
    # Without a monitoring source the ranges can only show their plan: that is setup, not trouble.
    try:
        return bool(sources.monitoring().enabled())
    except Exception:  # noqa: BLE001 - a source that can't even say is "set up but unreadable"
        return True


def seat_routes(now=None):
    """The seats whose traffic isn't on its planned firewall, for the plan's firewall layer: by seat,
    the firewall now (None: none left) and the planned one. Names only, never the IPs."""
    now = time.time() if now is None else now
    data = load_data()
    every = _parts(data)
    if not every:
        return {'enabled': False, 'seats': {}}
    status = {n: health.status(n, now) for row, _part, fw in every for n in [fw, *(row.get('fallback') or [])]}
    seats = {}
    for seat, ip in _seat_ips().items():
        found = _part_of(ip, every)
        if found is None:
            continue
        row, _part, fw = found
        now_on, state = _route([fw, *(row.get('fallback') or [])], status)
        if state in ('failover', 'down'):
            seats[seat] = {'now': now_on, 'intended': fw, 'state': state}
    return {'enabled': True, 'seats': seats}


def configured(data=None):
    """Are there firewalls in the inventory? Cheap: the health wall asks on every poll."""
    data = load_data() if data is None else data
    return any(d.get('role') == 'firewall' for d in inventory.devices(data))


def health_checks(now=None):
    """The firewalls as tiles of the service health wall (floorbit/health.py), so one going down, and
    its ranges failing over, reaches Discord like any other service."""
    if not configured():
        return []
    view = overview(now)
    by_planned = {}
    for r in view['ranges']:
        for p in r['parts']:
            by_planned.setdefault(p['firewall'], []).append(p)
    out = []
    for fw in view['firewalls']:
        status = {'online': 'up', 'offline': 'down'}.get(fw['status'], 'unknown')
        if fw['status'] == 'offline':
            moved = by_planned.get(fw['name'], [])
            lost = [r['cidr'] for r in moved if r['state'] == 'down']
            if lost:
                summary = f"{', '.join(lost)} without a firewall"
            elif moved:
                summary = f"{len(moved)} range{'s' if len(moved) != 1 else ''} failed over"
            else:
                summary = 'Down, serves no range'
        elif fw['serving']:
            n, seats = len(fw['serving']), fw['seats']
            summary = f"Serves {n} range{'s' if n != 1 else ''}, {seats} seat{'s' if seats != 1 else ''}"
        else:
            summary = 'Serves no range now'
        out.append({'id': f"firewall:{fw['id']}", 'name': fw['name'], 'kind': 'firewall', 'status': status,
                    'summary': summary, 'link': '/firewalls',
                    'metrics': [{'label': 'Seats', 'value': fw['seats'], 'unit': '', 'tone': ''}]
                    if status == 'up' else [],
                    'plugin': 'firewalls', 'plugin_name': 'Firewalls'})
    return out


def _route_of(ip, data, now):
    """The part ``ip`` falls in and the firewall it takes, or None when no range covers it."""
    found = _part_of(ip, _parts(data))
    if found is None:
        return None
    row, part, fw = found
    fallback = list(row.get('fallback') or [])
    line = [fw, *fallback]
    now_on, state = _route(line, {n: health.status(n, now) for n in line})
    return {'intended': fw, 'now': now_on, 'state': state, 'range': row.get('name') or '',
            'range_id': row['id'], 'cidr': row['cidr'], 'part': str(part), 'fallback': fallback}


SEAT_KEYS = ('intended', 'now', 'state', 'range', 'fallback')   # what a seat's answer may say: no address


def for_seat(seat, data=None, now=None):
    """Which firewall a seat's traffic should take and which it takes now, or None when no range
    covers its IP. Firewall names and address spans only, never the seat's IP: for the crew's seat panel."""
    now = time.time() if now is None else now
    data = load_data() if data is None else data
    if not _nets(data):
        return None
    ip = _seat_ips().get(str(seat or '').upper())
    found = _route_of(ip, data, now) if ip is not None else None
    return {k: found[k] for k in SEAT_KEYS} if found else None


def lookup(query, data=None, now=None, spans=True):
    """Which firewall an IP address or a seat goes through (Mike, 2026-11-24). A seat answers
    through its IP, which stays out of the answer; with ``spans`` False (no seats.view) so do the
    range and part it falls in, since a small part narrows it down. Raises FirewallError when the
    query is neither."""
    now = time.time() if now is None else now
    data = load_data() if data is None else data
    text = str(query or '').strip()
    if not text:
        raise FirewallError('Type an IP address or a seat.')
    try:
        ip, seat = ipaddress.ip_address(text), None
    except ValueError:
        seat = text.upper()
        ip = _seat_ips().get(seat)
        if ip is None:
            raise FirewallError(f'{text} is neither an IP address nor a seat with an IP address.', 404) from None
    found = _route_of(ip, data, now)
    if found and seat and not spans:
        found = {k: found[k] for k in (*SEAT_KEYS, 'range_id')}
    return {'query': text, 'kind': 'seat' if seat else 'ip', 'seat': seat, 'found': found is not None,
            **(found or {})}
