"""Crew walk-through check-in (docs/seat-walk.md): before doors open, the crew walk the rows with a
laptop, plug it into each seat's port and press Locate. Floorbit looks the laptop up from the
request's IP (ARP: IP to MAC, then the switches' MAC tables: MAC to switch port) and keeps
seat to port for this event, in the same place a seat check-in keeps it (integrations/checkin.py).

Cheapest fresh answer first, because every seat counts:

1. **The monitoring source** (``monitoring``): telemetry or LibreNMS, through the local agent when
   one is enrolled. Only as fresh as their last poll of the MAC tables, so an old answer is retried.
2. **Single SNMP GETs** (``snmp``) through the agent (floorbit/checkin_lookup.py): the switches of
   the seat's row (its area) first, then the rest of its block, then every switch with the VLAN.
3. **The switch itself** (``switch``), the last resort for switches that don't answer SNMP: over SSH
   with the stored login (floorbit/credentials.py), ``show mac address-table address <mac>`` on the
   switch the last seat was on (rows are mostly on one switch), then on the other switches.

Every step goes to the page as it happens (``Trace``, issue #1359).

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
from urllib.parse import urlsplit, urlunsplit

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


class Trace:
    """What one Locate does, step by step: the page shows it live while it runs (issue #1359).

    Each step is ``{"at": ms since the epoch, "code", "state", "ms"?, "args"}``; the page words it
    from ``code`` (``seatWalkTrace`` texts). ``state`` is ``ok``, ``no``, ``skip``, ``warn`` or ``run``
    (still going). With a ``run`` (the page's own random id for this Locate) every step also goes out
    on the live bus as ``seat-walk.trace``; the bus drops ``ip`` and ``mac`` for pages that may not
    read them (integrations/events.py), so a trace never shows a laptop to a kiosk.
    """
    MAX_STEPS = 300

    def __init__(self, run=None, seat=None, clock=time.time):
        self.run, self.seat, self.clock, self.steps = run, seat, clock, []

    def add(self, code, state='ok', ms=None, **args):
        step = {'at': int(self.clock() * 1000), 'code': code, 'state': state,
                'args': {k: v for k, v in args.items() if v is not None and v != []}}
        if ms is not None:
            step['ms'] = int(ms)
        if len(self.steps) < self.MAX_STEPS:
            self.steps.append(step)
            if self.run:
                from integrations import events
                events.publish('seat-walk.trace', {'run': self.run, 'seat': self.seat, 'step': step})
        return step


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


def port_from_switches(mac, registry, account, likely=(), trace=None):
    """``{"switch", "port"}`` where ``mac`` is on an access port now, or None. The likely switches
    first (the last seat's, the seat's patch plan), then every other switch at once."""
    trace = trace or Trace()
    switches = [d['name'] for d in _devices() if d.get('role') == 'switch']
    if not switches or _ssh(registry)[0] is None:
        return None
    first = [s for s in dict.fromkeys(likely) if s and any(_short(s).lower() == _short(x).lower() for x in switches)]
    rest = [s for s in switches if _short(s).lower() not in {_short(f).lower() for f in first}]
    for batch in ([first] if first else []) + [rest[i:i + MAX_CANDIDATES] for i in range(0, len(rest), MAX_CANDIDATES)]:
        hits = []
        trace.add('sshAsk', 'run', switches=batch, mac=mac)
        for result in _run(registry, account, batch, _mac_command(mac)):
            if not result.get('ok'):
                trace.add('sshSwitch', 'no', switch=result.get('switch'), result='error',
                          error=str(result.get('error') or '')[:200] or None)
                continue
            ups = _uplinks(result['switch'])
            seen = False
            for port in _parse_mac_table(result.get('output'), mac):
                seen = True
                if port.lower() in ups or UPLINK_NAME_RE.match(port):
                    trace.add('sshSwitch', 'skip', switch=result['switch'], port=port, result='uplink')
                    continue
                hits.append({'switch': result['switch'], 'port': port})
                trace.add('sshSwitch', 'ok', switch=result['switch'], port=port, result='found')
            if not seen:
                trace.add('sshSwitch', 'no', switch=result['switch'], result='none')
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


def _from_switches(ip, seat, mac, trace=None):
    """One PC's port with a few SNMP GETs through the agent (floorbit/checkin_lookup.py), or None."""
    from . import checkin_lookup
    try:
        got = checkin_lookup.lookup(ip, seat=seat, mac=mac, crew=True, trace=trace)
    except Exception as exc:  # noqa: BLE001  # SSH and the next try are still there
        print(f'[seat-walk] switch lookup failed: {exc}')
        if trace is not None:
            trace.add('snmpError', 'no', error=str(exc)[:200])
        return None, None
    found = {'switch': got['switch'], 'port': got['port']} if got.get('state') == 'found' else None
    return found, got


def locate_once(ip, registry=None, account=None, previous=None, likely=(), mac=None, seat=None, trace=None):
    """One try: ``{"found": {"switch", "port"} | None, "mac", "how", "steps": [...], "stale"}``.
    The tables first (LibreNMS, Telemetry), then single SNMP GETs on the switches through the agent
    (the seat row's switches, its block's, then every switch on the VLAN), and SSH last, for
    switches that don't answer SNMP. ``trace`` hears every step (issue #1359)."""
    trace = trace or Trace()
    steps, stale = [], False

    def old(port, how):
        trace.add('stale', 'warn', switch=port['switch'], port=port['port'], how=how)
        return True

    if not mac:
        mac, how = mac_for(ip, registry, account)
        steps.append({'step': 'mac', 'ok': bool(mac), 'how': how})
        trace.add('mac', 'ok' if mac else 'no', how=how, ip=ip, mac=mac)
    if mac:
        # The laptop may have a new lease in another seat block's network (or the crew typed only
        # its MAC): ask by the MAC. The IP we have still answers while ARP keeps it.
        with contextlib.suppress(Exception):
            ip = sources.monitoring().ip_for_mac(mac) or ip
    monitoring = sources.monitoring().enabled()
    asked_at = time.monotonic()
    port = _from_monitoring(ip) if ip and monitoring else None
    took = (time.monotonic() - asked_at) * 1000
    if port and port.get('mac') and not mac:
        mac = port['mac']
    if not monitoring:
        trace.add('monitoringOff', 'skip')
    if port and port.get('uplink'):
        steps.append({'step': 'monitoring', 'ok': False, 'how': 'uplink'})
        trace.add('monitoring', 'skip', ms=took, result='uplink')
        port = None
    else:
        steps.append({'step': 'monitoring', 'ok': bool(port)})
        if monitoring:
            trace.add('monitoring', 'ok' if port else 'no', ms=took, result='found' if port else 'none',
                      switch=(port or {}).get('switch'), port=(port or {}).get('port'))
    if port and _same(port, previous):
        stale, port = old(port, 'monitoring'), None
    if port:
        return {'found': {'switch': port['switch'], 'port': port['port']}, 'mac': mac, 'how': 'monitoring',
                'steps': steps, 'stale': False}
    if ip:
        port, got = _from_switches(ip, seat, mac, trace)
        if got and got.get('state') not in ('todo', 'closed'):
            steps.append({'step': 'snmp', 'ok': bool(port)})
        mac = mac or (got or {}).get('mac')
        if port and _same(port, previous):
            stale, port = old(port, 'snmp'), None
        if port:
            return {'found': port, 'mac': mac, 'how': 'snmp', 'steps': steps, 'stale': False}
    if mac and _ssh(registry)[0] is not None:
        port = port_from_switches(mac, registry, account, likely, trace)
        steps.append({'step': 'switch', 'ok': bool(port)})
        if port and _same(port, previous):
            stale, port = old(port, 'switch'), None
        if port:
            return {'found': port, 'mac': mac, 'how': 'switch', 'steps': steps, 'stale': False}
    return {'found': None, 'mac': mac, 'how': None, 'steps': steps, 'stale': stale}


def locate(ip, registry=None, account=None, previous=None, likely=(), mac=None, seconds=ATTEMPT_SECONDS,
           sleep=time.sleep, clock=time.monotonic, seat=None, trace=None):
    """Try for up to ``seconds``. The answer of the last try, with ``tries``. ``mac``: the laptop's,
    when the last seat already found it (it doesn't change from seat to seat)."""
    trace = trace or Trace()
    started, tries = clock(), 0
    while True:
        tries += 1
        result = locate_once(ip, registry, account, previous, likely, mac, seat, trace)
        mac = result['mac'] or mac
        if result['found']:
            trace.add('found', 'ok', ms=(clock() - started) * 1000, how=result['how'], **result['found'])
        elif clock() - started + RETRY_EVERY > seconds:
            trace.add('notFound', 'no', ms=(clock() - started) * 1000, tries=tries)
        else:
            trace.add('wait', 'run', seconds=RETRY_EVERY, attempt=tries + 1)
            sleep(RETRY_EVERY)
            continue
        return {**result, 'tries': tries, 'ms': int((clock() - started) * 1000), 'trace': trace.steps}


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


def _with_port(url, ports):
    """``url`` with the port the agent's host publishes its front door on, when the URL names none
    and it isn't the scheme's own (compose.yml's HTTPS_PUBLISH_PORT, issue #1361)."""
    parts = urlsplit(url)
    port = (ports or {}).get(parts.scheme)
    if not port or parts.port or port == {'https': 443, 'http': 80}.get(parts.scheme) or not parts.hostname:
        return url
    return urlunsplit(parts._replace(netloc=f'{parts.netloc}:{port}'))


def agent_url():
    """Where laptops on the event network reach a local agent, worked out, rarely typed in: a
    connected agent's "Reached in the hall at" (its page, or FLOORBIT_AGENT_HALL_URL in the hall),
    else the check-in name (CHECKIN_ADDRESS, already on every seat card, and every agent's front door
    answers it) on the port the agent is published on, else where browsers in the hall last reached
    an agent (each front door learns it from the requests it answers). '' while none is known."""
    from integrations import checkin

    from . import agent_link, agent_settings
    try:
        agents = [a for a in agent_link.all_agents() if a.get('connected')]
    except Exception as exc:  # noqa: BLE001  # no agents: the page says so
        print(f'[seat-walk] could not read the agents: {exc}')
        agents = []
    for a in agents:
        report = a.get('report') or {}
        said = ((report.get('settings') or {}).get('values') or {}).get('hall_url') or {}
        # The hall's own setting wins, as on the agent; else Floorbit's, also for an agent too old to know it.
        try:
            named = said.get('value') if said.get('source') == 'env' else (
                agent_settings.values(a['id']).get('hall_url') if a.get('id') else None)
        except agent_settings.AgentError:
            named = None
        if named:
            return str(named).rstrip('/')
    if checkin.hall_url():
        ports = next(((a.get('report') or {}).get('front_door_ports') for a in agents
                      if (a.get('report') or {}).get('front_door_ports')), None)
        return _with_port(checkin.hall_url(), ports)
    for a in agents:
        url = ((a.get('report') or {}).get('lan_url') or '').rstrip('/')
        if url:
            return url
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
            from . import seat_marks
            count += seat_marks.clear_all()
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
