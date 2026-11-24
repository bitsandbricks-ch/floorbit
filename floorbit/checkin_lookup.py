"""A check-in's PC, looked up on the switches when the tables don't know it yet (issue #947,
docs/segments.md).

A check-in (PIN, captive portal, the crew's seat walk) gives the PC's IP. When neither the mapping
nor the cached ARP/MAC tables (LibreNMS first, then Telemetry) know it, this asks the local agent to
find it with a few SNMP GETs:

1. the segment of the IP. Lookups off there (the default): no lookup, a to-do instead;
2. the MAC from the core's ARP entry on the segment's VLAN interface (skipped when the MAC is known);
3. the switches in order, the first hit on a port that isn't an uplink wins: the switches of the
   seat's row, then the block's, then every other switch with that VLAN.

Lookups run only inside the check-in window: from doors open (the schedule's event start) for
``hours`` (6 by default, per event), and on for 30 minutes after any check-in while it is open;
the crew can open it by hand. The seat walk asks anyway: the crew are standing at the seat.

The same IP or MAC asked again within a minute shares one lookup.
"""
import threading
import time

from .store import load_data, save_data

KEY = 'checkin_lookups'          # event data: {hours, opened_at, opened_by}
WINDOW_HOURS = 6
AFTER_ACTIVITY = 30 * 60
MEMO_SECONDS = 60
MAX_MEMO = 5000

_memo = {}                       # ip or mac -> (time, result)
_running = {}                    # ip or mac -> threading.Event while a lookup runs
_lock = threading.Lock()
_activity = {'at': 0.0}


class WindowError(Exception):
    status = 400


def settings(data=None):
    data = load_data() if data is None else data
    found = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    try:
        hours = max(1, min(48, int(found.get('hours') or WINDOW_HOURS)))
    except (TypeError, ValueError):
        hours = WINDOW_HOURS
    return {'hours': hours, 'opened_at': found.get('opened_at'), 'opened_by': found.get('opened_by')}


def window(now=None, data=None):
    """{open, until, why ('doors' | 'by_hand' | 'activity' | None), doors, hours}."""
    from . import schedule
    now = time.time() if now is None else now
    data = load_data() if data is None else data
    s = settings(data)
    span = s['hours'] * 3600
    doors = (schedule.get(data).get('event') or {}).get('start')
    ends = []
    if isinstance(doors, (int, float)) and doors <= now:
        ends.append((doors + span, 'doors'))
    if isinstance(s['opened_at'], (int, float)) and s['opened_at'] <= now:
        ends.append((s['opened_at'] + span, 'by_hand'))
    until, why = max(ends) if ends else (None, None)
    last = _activity['at']
    if last and until is not None and last <= until < last + AFTER_ACTIVITY:
        until, why = last + AFTER_ACTIVITY, 'activity'    # a check-in while open keeps it open a while
    is_open = until is not None and now < until
    return {'open': is_open, 'until': until if is_open else None, 'why': why if is_open else None,
            'doors': doors, 'hours': s['hours']}


def touch(now=None):
    """A check-in happened: while the window is open, it stays open AFTER_ACTIVITY longer."""
    now = time.time() if now is None else now
    if window(now)['open']:
        _activity['at'] = now


def open_window(by, hours=None, now=None):
    from .blueprints.inventory import data_lock
    now = time.time() if now is None else now
    with data_lock:
        data = load_data()
        s = settings(data)
        if hours is not None:
            try:
                s['hours'] = max(1, min(48, int(hours)))
            except (TypeError, ValueError):
                raise WindowError('Give the hours as a number from 1 to 48.') from None
        data[KEY] = {'hours': s['hours'], 'opened_at': now, 'opened_by': by}
        save_data(data)
    return window(now)


def close_window(by, now=None):
    from .blueprints.inventory import data_lock
    now = time.time() if now is None else now
    with data_lock:
        data = load_data()
        s = settings(data)
        data[KEY] = {'hours': s['hours'], 'opened_at': None, 'opened_by': by}
        save_data(data)
    _activity['at'] = 0.0
    return window(now)


# ── which switches to ask ──────────────────────────────────────────────────────────────────────

def _block_rows(seat, data):
    """(the seat's row, the rest of its block), as seat names; ([], []) for a seat in no block."""
    from .seat_names import block_rows
    seat = str(seat or '').upper()
    for block in data.get('seat_blocks') or []:
        try:
            rows = [[s.upper() for s in row] for row in block_rows(block)]
        except Exception:  # noqa: BLE001  # one odd block must not stop a lookup
            continue
        for row in rows:
            if seat in row:
                return row, [s for r in rows if r is not row for s in r]
    return [], []


def _switches_of(seats, data):
    """The switches that serve these seats: their learned ports, then the patch plan's cables, then
    the switches whose area holds them (pins and plan position, floorbit/switch_areas.py)."""
    from integrations import checkin

    from . import cables, switch_areas
    wanted = set(seats)
    out = []
    for seat, port in sorted(checkin.learned_ports().items()):
        if seat in wanted and port.get('switch'):
            out.append(port['switch'])
    for c in cables.all_cables(data):
        if str(c.get('seat') or '').upper() in wanted and c.get('switch'):
            out.append(c['switch'])
    out += switch_areas.switches_for(wanted, data)
    return list(dict.fromkeys(out))


def _vlan_switches(vlan, data):
    """Every switch the telemetry knows to carry ``vlan`` (or whose VLANs it doesn't know)."""
    from .telemetry import targets
    out = []
    for t in targets.listing(data):
        if t.get('kind', 'switch') != 'switch' or 'snmp' not in (t.get('drivers') or []) or t.get('fdb') == 'off':
            continue
        if not t.get('vlans') or vlan in t['vlans']:
            out.append(t['name'])
    return out


def candidate_groups(seat, vlan, data=None):
    """``{"row": [...], "block": [...], "vlan": [...]}``: the switches to ask, in order and each once:
    the seat's row (its area), the rest of its block, then every other switch with the VLAN."""
    data = load_data() if data is None else data
    row, block = _block_rows(seat, data)
    seen, out = set(), {}
    for group, names in (('row', _switches_of(row, data) if row else []),
                         ('block', _switches_of(block, data) if block else []),
                         ('vlan', _vlan_switches(vlan, data))):
        out[group] = [n for n in names if not (n in seen or seen.add(n))]
    return out


def candidates(seat, vlan, data=None):
    """Switch names in the order to ask: the seat's row, its block, the rest with the VLAN."""
    return [n for names in candidate_groups(seat, vlan, data).values() for n in names]


def _core(seg, data):
    """(core device name, VLAN interface ifIndex) for the segment, from discovery."""
    from . import segments
    if seg.get('device') and seg.get('if_index'):
        return seg['device'], seg['if_index']
    for p in segments.proposals(data):
        if p['network'] == seg.get('network') and p.get('device') and p.get('if_index'):
            return p['device'], p['if_index']
    return None, None


# ── the lookup ─────────────────────────────────────────────────────────────────────────────────

def _ask_agents(req):
    """The first agent's answer that found the port, else the last answer. Raises PluginError."""
    from . import agent_plugins, sources
    from .plugins.base import PluginError
    # No app context here: the check-in verifier runs in its own thread.
    spec = sources.registry.specs.get('telemetry') if sources.registry is not None else None
    if spec is None:
        raise PluginError('The Telemetry plugin is missing.')
    answers = agent_plugins.ask(spec, 'call', 'lookup', req)
    good = [a['result'] for a in answers if isinstance(a.get('result'), dict) and not a['result'].get('error')]
    found = next((r for r in good if r.get('switch')), None)
    if found:
        return found
    if good:
        merged = dict(good[0])
        merged['mac'] = next((r['mac'] for r in good if r.get('mac')), None)
        return merged
    raise PluginError('; '.join(str(a.get('error') or (a.get('result') or {}).get('error')) for a in answers)[:300]
                      or 'No local agent answered.')


def lookup(ip, seat=None, mac=None, crew=False, now=None, ask=None, data=None, trace=None):
    """``{state, switch?, port?, mac?, todo?, ...}``. ``state``:

    - ``found``: a switch learned it on an access port;
    - ``not_found``: asked, nobody knew it (yet);
    - ``todo``: can't ask (``todo``: ``no_segment``, ``segment_off``, ``no_core``): crew types the
      MAC or picks the port;
    - ``closed``: outside the check-in window;
    - ``error``: the agent didn't answer.

    ``trace`` (the seat walk's, floorbit/seat_walk.py) hears which switches are asked and what each said.
    """
    from . import segments
    now = time.time() if now is None else now
    data = load_data() if data is None else data
    seg = segments.for_ip(ip, segments.all_segments()) if ip else None
    if seg is None:
        _said(trace, 'snmpTodo', 'skip', why='no_segment', ip=ip)
        return {'state': 'todo', 'todo': 'no_segment'}
    if not seg.get('lookups'):
        _said(trace, 'snmpTodo', 'skip', why='segment_off', vlan=seg['vlan'])
        return {'state': 'todo', 'todo': 'segment_off', 'vlan': seg['vlan']}
    if not crew and not window(now, data)['open']:
        return {'state': 'closed', 'vlan': seg['vlan']}
    key = str(mac or ip)
    while True:
        with _lock:
            hit = _memo.get(key)
            # The seat walk moves one laptop from seat to seat: its answer from a minute ago is
            # the last seat's, so the crew always ask afresh.
            if hit and not crew and now - hit[0] < MEMO_SECONDS:
                return hit[1]
            running = _running.get(key)
            if running is None:
                running = _running[key] = threading.Event()
                break
        running.wait(30)          # someone else asks right now: share their answer
        now = time.time()
    try:
        result = _lookup(ip, seat, mac, seg, data, ask or _ask_agents, trace)
        with _lock:
            if len(_memo) >= MAX_MEMO:
                _memo.clear()
            _memo[key] = (time.time(), result)
        return result
    finally:
        with _lock:
            _running.pop(key, None)
        running.set()


def _said(trace, code, state, **args):
    if trace is not None:
        trace.add(code, state, **args)


def _lookup(ip, seat, mac, seg, data, ask, trace=None):
    from .plugins.base import PluginError
    vlan = seg['vlan']
    core, if_index = _core(seg, data)
    if not mac and not core:
        _said(trace, 'snmpTodo', 'skip', why='no_core', vlan=vlan)
        return {'state': 'todo', 'todo': 'no_core', 'vlan': vlan}
    groups = candidate_groups(seat, vlan, data)
    req = {'ip': ip, 'vlan': vlan, 'if_index': if_index, 'core': core, 'mac': mac,
           'switches': [n for names in groups.values() for n in names]}
    if not mac:
        _said(trace, 'snmpArp', 'run', core=core, vlan=vlan, ip=ip)
    _said(trace, 'snmpAsk', 'run', vlan=vlan, row=groups['row'], block=groups['block'], others=len(groups['vlan']))
    try:
        got = ask(req)
    except PluginError as exc:
        print(f'[check-in] lookup of {ip} in VLAN {vlan} failed: {exc}')
        _said(trace, 'snmpError', 'no', error=str(exc)[:200])
        return {'state': 'error', 'vlan': vlan}
    if trace is not None:
        _trail(trace, got, groups, mac)
    out = {'vlan': vlan, 'mac': got.get('mac'), 'asked': len(got.get('asked') or []),
           'took_ms': got.get('took_ms')}
    if got.get('switch') and (got.get('port') or got.get('if_index')):
        out.update(state='found', switch=got['switch'], port=got.get('port') or str(got['if_index']))
        _remember(ip, out)
    else:
        out['state'] = 'not_found'
    return out


def _trail(trace, got, groups, mac):
    """What each switch said, from the agent's ``trail`` (agents built on a Floorbit before issue
    #1359 send only ``asked``, ``skipped`` and ``errors``, so it is worked out from those)."""
    group_of = {n: g for g, names in groups.items() for n in names}
    if not mac:
        trace.add('snmpMac', 'ok' if got.get('mac') else 'no', mac=got.get('mac'))
        if not got.get('mac'):
            return
    trail = got.get('trail')
    if not isinstance(trail, list):
        errors = {e.get('switch'): e.get('error') for e in got.get('errors') or [] if isinstance(e, dict)}
        uplinks = {s.get('switch'): s.get('if_index') for s in got.get('skipped') or [] if isinstance(s, dict)}
        trail = []
        for name in got.get('asked') or []:
            if name == got.get('switch'):
                trail.append({'switch': name, 'result': 'found', 'port': got.get('port') or got.get('if_index')})
            elif name in uplinks:
                trail.append({'switch': name, 'result': 'uplink', 'if_index': uplinks[name]})
            else:
                trail.append({'switch': name, 'result': 'error' if name in errors else 'none',
                              'error': errors.get(name)})
    errors = {e.get('switch'): e.get('error') for e in got.get('errors') or [] if isinstance(e, dict)}
    for step in trail[:64]:
        if not isinstance(step, dict):
            continue
        name, result = str(step.get('switch') or ''), str(step.get('result') or 'none')
        args = {'switch': name, 'group': group_of.get(name, 'vlan'), 'result': result,
                'port': step.get('port') or (str(step['if_index']) if step.get('if_index') else None)}
        if result == 'error':
            args['error'] = str(step.get('error') or errors.get(name) or '')[:200]
        state = 'ok' if result == 'found' else 'skip' if result == 'uplink' else 'no'
        trace.add('snmpSwitch', state, ms=step.get('ms'), **args)


def _remember(ip, found):
    """Into the IP/MAC history, so search and the port's page know it at once."""
    from . import endpoints
    try:
        endpoints.history().record([{'mac': found.get('mac'), 'ip': ip, 'device': found['switch'],
                                     'port': found['port'], 'vlan': found.get('vlan')}])
    except Exception as exc:  # noqa: BLE001  # history is a convenience: the check-in has its answer
        print(f'[check-in] could not keep the lookup in the history: {exc}')


def reset():
    """Tests: forget what was asked."""
    with _lock:
        _memo.clear()
        _running.clear()
    _activity['at'] = 0.0
