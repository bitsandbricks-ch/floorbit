"""Crew walk-through check-in (docs/seat-walk.md): before doors open, the crew walk the rows with a
laptop, plug it into each seat's port and press Locate. Floorbit looks the laptop up from the
request's IP (ARP: IP to MAC, then the switches' MAC tables: MAC to switch port) and keeps
seat to port for this event, in the same place a seat check-in keeps it (integrations/checkin.py).

Freshest answer first, because every seat counts:

1. **The switch itself** (``switch``): over SSH with the stored login (floorbit/credentials.py), ask
   ``show mac address-table address <mac>`` on the switch the last seat was on (rows are mostly on
   one switch), then on the other switches. One to three seconds.
2. **The monitoring source** (``monitoring``): telemetry or LibreNMS, through the local agent when
   one is enrolled. Only as fresh as their last poll of the MAC tables, so this is retried.

The laptop keeps its IP and MAC from seat to seat; only its port changes. So an answer that still
names the last seat's port is old (a MAC table nobody read again yet) and is not taken.

**Behind NAT or hosted**, the request's address is the hall's public one. Then the laptop says
hello through the local agent once (``hello``): the page sends the browser to the agent's address
on the event network with a one-time code, the agent sees the laptop's own IP and reports it over
its link, and the walk goes on with that IP and, once found, the laptop's MAC.

A mapping belongs to the event (it is a document of the event's folder) and is cleared one day
after the event ends: the end in its schedule, else when it was closed (``purge_ended``).
"""
import contextlib
import ipaddress
import re
import secrets
import threading
import time

from integrations import checkin

from . import audit, cables, edge_ports, inventory, sources
from .store import load_data

ATTEMPT_SECONDS = 20       # one request keeps trying this long; the page asks again after
RETRY_EVERY = 3
KEEP_AFTER_END = 24 * 3600
MAX_CANDIDATES = 12        # switches asked at once when the likely ones didn't have the MAC
MAC_RE = re.compile(r'\b([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}|(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2})\b', re.I)
UPLINK_NAME_RE = re.compile(r'^(po|port-channel|vlan|vl|nve|tunnel|mgmt|lag|ae)\s*\d', re.I)
SOURCE = 'walk'


class WalkError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _mac(text):
    return sources.normalise_mac(text) if text else None


def _same(a, b):
    from .syslog import canonical_port
    return bool(a and b and str(a.get('switch') or '').lower().split('.')[0]
                == str(b.get('switch') or '').lower().split('.')[0]
                and canonical_port(a.get('port') or '') == canonical_port(b.get('port') or ''))


def _short(name):
    return str(name or '').split('.')[0]


# ── IP to MAC ──────────────────────────────────────────────────────────────────────────────────

def mac_for(ip, registry=None, account=None):
    """The laptop's MAC, from what is known already, else from the routers' ARP over SSH.
    ``(mac, how)`` or ``(None, None)``."""
    monitor = sources.monitoring()
    try:
        if monitor.enabled():
            mac = _mac(monitor.mac_for_ip(ip))
            if mac:
                return mac, 'monitoring'
    except Exception as exc:  # noqa: BLE001  # the other ways still answer
        print(f'[seat-walk] ARP from the monitoring source failed: {exc}')
    try:
        from . import endpoints
        for row in endpoints.history().search(ip, limit=5):
            if row.get('ip') == ip and row.get('mac'):
                return _mac(row['mac']), 'history'
    except Exception as exc:  # noqa: BLE001
        print(f'[seat-walk] endpoint history failed: {exc}')
    if registry is not None:
        routers = [d['name'] for d in _devices() if d.get('role') == 'router']
        for result in _run(registry, account, routers, f'show ip arp {ip}'):
            for line in (result.get('output') or '').splitlines():
                if ip in line.split():
                    found = MAC_RE.search(line)
                    if found:
                        return _mac(found.group(1)), 'switch'
    return None, None


# ── MAC to port, from the switches themselves ──────────────────────────────────────────────────

def _devices():
    return [d for d in inventory.devices(load_data(), include_hidden=True) if d.get('mgmt_ip')]


def _ssh(registry):
    """The plugin that runs show commands, if a login for it needs no typing."""
    from . import commands, ports
    spec = commands.plugin(registry) if registry is not None else None
    if spec is None:
        return None, False
    return spec, ports.info(registry)['plugin_login']


def _run(registry, account, names, command):
    """``command`` on the switches a login is stored for (or that need none). Never asks anyone."""
    from . import commands, credentials
    spec, needs_login = _ssh(registry)
    if spec is None or not names:
        return []
    names = [n for n in dict.fromkeys(names) if not needs_login or credentials.covers(n)]
    if not names:
        return []
    try:
        return commands.run_on(registry, spec, account or 'seat walk', {'switches': names[:commands.MAX_SWITCHES]},
                               [command], max_output=16 * 1024)
    except commands.CommandError as exc:
        print(f'[seat-walk] {command} failed: {exc}')
        return []


def _uplinks(switch):
    """Ports of ``switch`` that lead to another switch (LLDP/CDP): the MAC shows up there too."""
    try:
        return {str(n.get('port') or '').lower() for n in sources.monitoring().neighbours(switch) or []}
    except Exception:  # noqa: BLE001  # no neighbours known: the port names still help
        return set()


def _parse_mac_table(output, mac):
    """Ports on which this MAC table shows ``mac``: IOS, NX-OS and most others print the port
    last on the line."""
    out = []
    for line in str(output or '').splitlines():
        found = MAC_RE.search(line)
        if not found or _mac(found.group(1)) != mac:
            continue
        words = line.replace('*', ' ').split()
        if words:
            out.append(words[-1])
    return out


def _mac_command(mac):
    digits = mac.replace(':', '')
    return f'show mac address-table address {digits[0:4]}.{digits[4:8]}.{digits[8:12]}'


def port_from_switches(mac, registry, account, likely=()):
    """``{"switch", "port"}`` where ``mac`` is on an access port now, or None. The likely switches
    first (the last seat's, the seat's patch plan), then every other switch at once."""
    switches = [d['name'] for d in _devices() if d.get('role') == 'switch']
    if not switches or _ssh(registry)[0] is None:
        return None
    first = [s for s in dict.fromkeys(likely) if s and any(_short(s).lower() == _short(x).lower() for x in switches)]
    rest = [s for s in switches if _short(s).lower() not in {_short(f).lower() for f in first}]
    for batch in ([first] if first else []) + [rest[i:i + MAX_CANDIDATES] for i in range(0, len(rest), MAX_CANDIDATES)]:
        hits = []
        for result in _run(registry, account, batch, _mac_command(mac)):
            if not result.get('ok'):
                continue
            ups = _uplinks(result['switch'])
            for port in _parse_mac_table(result.get('output'), mac):
                if port.lower() in ups or UPLINK_NAME_RE.match(port):
                    continue
                hits.append({'switch': result['switch'], 'port': port})
        if len(hits) == 1:
            return hits[0]
        if hits:
            # Seen on several access ports: an uplink LLDP didn't name. The access-style name wins
            # (Gi1/0/7 before Te1/1/1); still unsure, nothing.
            access = [h for h in hits if re.match(r'^(gi|fa|eth?|ge)', h['port'], re.I)]
            return access[0] if len(access) == 1 else None
    return None


# ── one lookup ─────────────────────────────────────────────────────────────────────────────────

def _from_monitoring(ip):
    monitor = sources.monitoring()
    if not monitor.enabled():
        return None
    try:
        found = monitor.resolve_ip(ip)
    except Exception as exc:  # noqa: BLE001
        print(f'[seat-walk] monitoring lookup failed: {exc}')
        return None
    if isinstance(found, dict) and 'value' in found and not found.get('port'):
        found = found.get('value')       # a stale answer: the last good one
    if not isinstance(found, dict) or not found.get('port'):
        return None
    if not edge_ports.is_edge(found.get('macs_on_port')):
        # Only an uplink or a desk switch still has the MAC (the access switch aged it out or
        # isn't polled): saving that as the seat's port would be wrong. The MAC still helps the
        # switch lookup that comes next.
        return {'switch': None, 'port': None, 'mac': _mac(found.get('mac')), 'uplink': True}
    return {'switch': found.get('device_name') or _short(found.get('hostname')), 'port': found['port'],
            'mac': _mac(found.get('mac'))}


def _from_switches(ip, seat, mac):
    """One PC's port with a few SNMP GETs through the agent (floorbit/checkin_lookup.py), or None."""
    from . import checkin_lookup
    try:
        got = checkin_lookup.lookup(ip, seat=seat, mac=mac, crew=True)
    except Exception as exc:  # noqa: BLE001  # SSH and the next try are still there
        print(f'[seat-walk] switch lookup failed: {exc}')
        return None, None
    found = {'switch': got['switch'], 'port': got['port']} if got.get('state') == 'found' else None
    return found, got


def locate_once(ip, registry=None, account=None, previous=None, likely=(), mac=None, seat=None):
    """One try: ``{"found": {"switch", "port"} | None, "mac", "how", "steps": [...], "stale"}``.
    The tables first (LibreNMS, Telemetry), then single SNMP GETs on the switches, and SSH last,
    for switches that don't answer SNMP."""
    steps, stale = [], False
    if not mac:
        mac, how = mac_for(ip, registry, account)
        steps.append({'step': 'mac', 'ok': bool(mac), 'how': how})
    if mac:
        # The laptop may have a new lease in another seat block's network (or the crew typed only
        # its MAC): ask by the MAC. The IP we have still answers while ARP keeps it.
        with contextlib.suppress(Exception):
            ip = sources.monitoring().ip_for_mac(mac) or ip
    port = _from_monitoring(ip) if ip else None
    if port and port.get('mac') and not mac:
        mac = port['mac']
    if port and port.get('uplink'):
        steps.append({'step': 'monitoring', 'ok': False, 'how': 'uplink'})
        port = None
    else:
        steps.append({'step': 'monitoring', 'ok': bool(port)})
    if port and _same(port, previous):
        stale, port = True, None
    if port:
        return {'found': {'switch': port['switch'], 'port': port['port']}, 'mac': mac, 'how': 'monitoring',
                'steps': steps, 'stale': False}
    if ip:
        port, got = _from_switches(ip, seat, mac)
        if got and got.get('state') not in ('todo', 'closed'):
            steps.append({'step': 'snmp', 'ok': bool(port)})
        mac = mac or (got or {}).get('mac')
        if port and _same(port, previous):
            stale, port = True, None
        if port:
            return {'found': port, 'mac': mac, 'how': 'snmp', 'steps': steps, 'stale': False}
    if mac and _ssh(registry)[0] is not None:
        port = port_from_switches(mac, registry, account, likely)
        steps.append({'step': 'switch', 'ok': bool(port)})
        if port and _same(port, previous):
            stale, port = True, None
        if port:
            return {'found': port, 'mac': mac, 'how': 'switch', 'steps': steps, 'stale': False}
    return {'found': None, 'mac': mac, 'how': None, 'steps': steps, 'stale': stale}


def locate(ip, registry=None, account=None, previous=None, likely=(), mac=None, seconds=ATTEMPT_SECONDS,
           sleep=time.sleep, clock=time.monotonic, seat=None):
    """Try for up to ``seconds``. The answer of the last try, with ``tries``. ``mac``: the laptop's,
    when the last seat already found it (it doesn't change from seat to seat)."""
    started, tries = clock(), 0
    while True:
        tries += 1
        result = locate_once(ip, registry, account, previous, likely, mac, seat)
        mac = result['mac'] or mac
        if result['found'] or clock() - started + RETRY_EVERY > seconds:
            return {**result, 'tries': tries, 'ms': int((clock() - started) * 1000)}
        sleep(RETRY_EVERY)


# ── the laptop's own address, through the local agent ───────────────────────────────────────────

HELLO_SECONDS = 10 * 60     # a code is good this long after the page asked for it
HELLO_KEEP = 12 * 3600      # and the laptop it named is remembered this long (a walk's length)
TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{16,64}\Z')
_hello_lock = threading.Lock()


def _hellos_path():
    from . import store
    return store.event_path('seat_walk_hellos.json')


def _hellos(now):
    """The codes, without the old ones. A document, so every pod sees the agent's report."""
    from . import store
    rows = store.read_json(_hellos_path(), {}) or {}
    return {t: r for t, r in rows.items() if isinstance(r, dict)
            and now - (r.get('at') or 0) < (HELLO_KEEP if r.get('ip') else HELLO_SECONDS)}


def private_ip(ip):
    try:
        addr = ipaddress.ip_address(str(ip or '').strip())
    except ValueError:
        return False
    return addr.is_private and not addr.is_loopback


def agent_url():
    """Where laptops on the event network reach a local agent, worked out, never typed in: the
    check-in name (CHECKIN_ADDRESS, already on every seat card, and every agent's front door answers
    it), else where browsers in the hall last reached an agent (each front door learns it from the
    requests it answers). '' while neither is known."""
    from integrations import checkin

    from . import agent_link
    if checkin.hall_url():
        return checkin.hall_url()
    try:
        for a in agent_link.all_agents():
            url = ((a.get('report') or {}).get('lan_url') or '').rstrip('/')
            if a.get('connected') and url:
                return url
    except Exception as exc:  # noqa: BLE001  # no agents: the page says so
        print(f'[seat-walk] could not read the agents: {exc}')
    return ''


def hello_here(token, ip, agent_name, now=None):
    """The page itself came through an agent's front door: that agent already saw the laptop's
    address, so the hello is done without the trip."""
    return agent_said_hello(token, ip, agent_name, now)


def new_hello(by, now=None):
    """A one-time code for the laptop to take through the agent."""
    from . import store
    now = time.time() if now is None else now
    token = secrets.token_urlsafe(18)
    with _hello_lock:
        rows = _hellos(now)
        if len(rows) > 500:
            raise WalkError('Too many walk-throughs are waiting for their laptop.', 429)
        rows[token] = {'at': now, 'by': by}
        store.write_json(_hellos_path(), rows)
    return token


def agent_said_hello(token, ip, agent_name, now=None):
    """The agent saw the laptop with this code at ``ip``. False for an unknown or used code."""
    from . import store
    now = time.time() if now is None else now
    if not TOKEN_RE.match(str(token or '')) or not private_ip(ip):
        return False
    with _hello_lock:
        rows = _hellos(now)
        row = rows.get(token)
        if row is None or row.get('ip'):
            return False
        row.update(ip=str(ipaddress.ip_address(ip)), agent=str(agent_name or '')[:60], at=now)
        store.write_json(_hellos_path(), rows)
    return True


def hello(token, now=None):
    """``{"ip", "agent", "at"}`` once the agent saw the laptop, ``{}`` while waiting, None when unknown."""
    if not TOKEN_RE.match(str(token or '')):
        return None
    row = _hellos(time.time() if now is None else now).get(token)
    if row is None:
        return None
    return {k: row[k] for k in ('ip', 'agent', 'at') if row.get('ip')}


# ── keeping it ─────────────────────────────────────────────────────────────────────────────────

def likely_switches(seat, previous=None):
    """Where to look first: the switch of the seat walked just before, the patch plan's."""
    out = [previous.get('switch')] if previous and previous.get('switch') else []
    for c in cables.all_cables():
        if (c.get('seat') or '').upper() == seat:
            out.append(c['switch'])
    held = checkin.learned_ports().get(seat)
    if held:
        out.append(held['switch'])
    return out


def save(seat, port, by, now=None):
    """Seat ``seat`` is on ``port``: kept for this event. Another seat that had this port loses it
    (the crew just plugged in here). Returns ``{"replaced": [seats], "plan_seat"}``: the patch plan
    naming another seat for this port wins over a walk, so the page offers to correct it."""
    from .syslog import canonical_port
    key = (port['switch'].lower(), canonical_port(port['port']))
    replaced = []
    for other, row in checkin.learned_ports().items():
        if other != seat and (str(row.get('switch') or '').lower(), canonical_port(row.get('port') or '')) == key:
            checkin.forget_port(other)
            replaced.append(other)
    checkin.learn_port(seat, port, by, now=now, source=SOURCE)
    plan = cables.port_seats(learned=False).get(key)
    target = ' '.join([port['switch'], port['port']] + [f'(was {s})' for s in replaced])
    audit.record('check-in', f'Walk-through: seat {seat} found on its port', by, target)
    return {'replaced': replaced, 'plan_seat': plan if plan and plan != seat else None}


def seats(row_ids, order='rows', data=None):
    """The picked rows' seats in walking order (rows in the order picked), each with the port it has
    in this event so far. A walker takes a row or a few, not a whole block."""
    from . import seat_names
    data = load_data() if data is None else data
    try:
        rows = seat_names.pick_rows(data, row_ids)
    except ValueError:
        raise WalkError('That row is not on the floor plan any more.', 404) from None
    if not rows:
        raise WalkError('Pick a row.', 404)
    if order not in ('rows', 'snake'):
        raise WalkError('The order is rows or snake.')
    out = []
    for i, row in enumerate(rows):
        out += list(reversed(row['seats'])) if order == 'snake' and i % 2 else row['seats']
    learned = checkin.learned_ports()
    return {'rows': [r['id'] for r in rows], 'row_names': [r['name'] for r in rows], 'seats': [
        {'seat': s, 'port': ({k: learned[s].get(k) for k in ('switch', 'port', 'learned_at', 'source')}
                             if s in learned else None)} for s in out]}


# ── retention ──────────────────────────────────────────────────────────────────────────────────

def event_end(event, data):
    """When the event ended: its schedule's end (or start, for a one-day event without an end), else
    when it was closed. None while nobody can tell."""
    from . import schedule
    window = schedule.get(data).get('event') or {}
    end = window.get('end') or None
    if end is None and event.get('status') == 'closed':
        end = event.get('closed_at')
    return end


def purge_ended(now=None):
    """Forget the seat ports of every event that ended more than a day ago. Returns the event ids."""
    from . import tenancy
    now = time.time() if now is None else now
    cleared = []
    for event in tenancy.events():
        with tenancy.using_event(event):
            try:
                end = event_end(event, load_data())
            except Exception as exc:  # noqa: BLE001  # one broken event must not stop the others
                print(f"[seat-walk] could not read {event['id']}'s schedule: {exc}")
                continue
            if end is None or now < end + KEEP_AFTER_END:
                continue
            count = checkin.forget_all_ports()
            if count:
                cleared.append(event['id'])
                audit.record('check-in', f'Cleared {count} seat ports one day after the event ended', 'Floorbit',
                             event.get('name') or event['id'])
    return cleared


def _loop(app, stop):
    from . import cluster
    while not stop.wait(3600):
        try:
            if cluster.leading():
                with app.app_context():
                    purge_ended()
        except Exception as exc:  # noqa: BLE001  # the loop must outlive one bad run
            print(f'[seat-walk] clearing old seat ports failed: {exc}')


def init_app(app, start_background=True):
    if not start_background:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(app, stop), name='seat-walk-retention', daemon=True).start()
    return stop
