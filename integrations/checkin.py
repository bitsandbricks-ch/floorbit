"""Seat check-in: people tell us their seat, we record their IP and MAC.

A small page at ``/checkin`` asks for seat number and username. The server
takes the request's source IP, looks up the MAC for that IP in LibreNMS' ARP
data, and stores one row per seat:

    seat, username, ip, mac, checked_in_at, last_seen, ip_changed

This is exposed as the ``checkin`` seat source, so ``SEAT_SOURCES=checkin,json``
puts check-ins in front of the static file.

Things that make an IP wrong, and what this does about them:

* NAT / proxies: the PC's address comes only from the local agent's front
  door (``attendee_ip``), which answers on the event network and passes on the
  address it saw. A request that didn't come through it still checks in the
  seat and nick, without an address or port. ``CHECKIN_ALLOWED_NETWORKS``
  (CIDRs, e.g. ``10.0.0.0/16``) rejects check-ins from outside the player
  networks, and from outside the front door, instead.
* DHCP leases: the MAC is treated as the stable identity. A background refresh
  (``CHECKIN_REFRESH_INTERVAL``) asks LibreNMS which IP that MAC has now and
  updates the row; ``ip_changed`` records when that happened.
* One machine, one seat: checking in from an IP or MAC that already holds
  another seat moves it.

From a PC (docs/seat-mapping.md, "Checking in from a PC"): nobody has to scan the QR code.
Every seat card carries the short address (``CHECKIN_ADDRESS``, e.g. checkin.lan) and the seat's
PIN. The attendee types the PIN and their nick, never the seat: the PIN names it. The request's
IP gives the switch port (ARP on the core, then the access switches' MAC tables), and the seat to
port pair is kept (``learned_ports``). That pair is what lasts; the seat then shows the port's
current MAC and IP. Ports that disagree go to the Problems page.
"""
import hmac
import ipaddress
import json
import os
import re
import secrets
import threading
import time

from flask import request

from . import config, events, history, seat_sources

_lock = threading.RLock()
SEAT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _\-]{0,15}$')
USER_RE = re.compile(r'^[^\x00-\x1f<>]{1,48}$')


def _path():
    from floorbit import store
    return store.event_file(config.get('CHECKIN_FILE', 'checkins.json'))


def load_all():
    with _lock:
        from floorbit import store
        try:
            return store.read_json(_path(), {})
        except json.JSONDecodeError:
            return {}


def _save_all(rows):
    from floorbit import store
    store.write_json(_path(), rows)


# ── ARP lookups (through the monitoring plugin, e.g. LibreNMS) ──────────────
def _monitoring():
    from floorbit import sources
    return sources.monitoring()


def normalise_mac(mac):
    from floorbit.sources import normalise_mac as norm
    return norm(mac) if mac else None


def lookup_mac(ip):
    """IP → MAC from the monitoring plugin's ARP data (None if unknown)."""
    return _monitoring().mac_for_ip(ip)


def lookup_ip(mac):
    """MAC → current IP from the monitoring plugin's ARP data (None if unknown)."""
    return _monitoring().ip_for_mac(mac)


# ── request helpers ──────────────────────────────────────────────────────────
def front_door_host():
    """The name the attendee typed, when the agent's front door passed the request on (it can't keep
    the Host header: the request goes to the hosted Floorbit's own name). None otherwise."""
    key = request.headers.get('Floorbit-Front-Door')
    if not key:
        return None
    from floorbit import agent_link
    return request.headers.get('Floorbit-Front-Door-Host') if agent_link.front_door(key) else None


def _front_door_ip():
    """The attendee's own address, when the local agent's front door passed the request on (the
    agent's front_door.py): it sets the address it saw, with its key, so a hosted Floorbit behind the
    hall's NAT still knows which PC asks. Without a valid key the header means nothing."""
    key = request.headers.get('Floorbit-Front-Door')
    if not key:
        return None
    from floorbit import agent_link
    if not agent_link.front_door(key):
        return None
    try:
        return str(ipaddress.ip_address(request.headers.get('Floorbit-Client-IP', '').strip()))
    except ValueError:
        return None



_proxy_hint = {'logged': False}


def attendee_ip():
    """The address that names the attendee's PC for check-in: only the one the local agent's front
    door saw. One way for hosted and self-hosted alike: the server never takes a request's own
    address (or X-Forwarded-For) as the seat PC's, because behind NAT or a proxy that is somebody
    else's. None when the request didn't come through the front door."""
    return _front_door_ip()


def client_ip():
    """Who is asking, for per-client limits and the sign-in lockout: the front door's address,
    else the request's (``CHECKIN_TRUST_PROXY``). Never the seat PC's address: see attendee_ip."""
    door = _front_door_ip()
    if door:
        return door
    ip = request.remote_addr or ''
    if not config.get_bool('CHECKIN_TRUST_PROXY', False):
        if not _proxy_hint['logged'] and request.headers.get('X-Forwarded-For'):
            # Every client then looks like the proxy: one guesser locks a username for everyone.
            _proxy_hint['logged'] = True
            print(f'[proxy] Requests arrive through a proxy at {ip}, but CHECKIN_TRUST_PROXY is off: '
                  'every client counts as that one address for check-in, the sign-in lockout and the '
                  "per-client limits. Turn it on if only your proxy can reach Floorbit's port.")
    else:
        # Proxies append the address they saw, so only the last ones are trustworthy: the leftmost
        # entry is whatever the client sent, and taking it let anyone pick their own address
        # (check in as another seat, dodge the sign-in lockout).
        forwarded = [a.strip() for a in request.headers.get('X-Forwarded-For', '').split(',') if a.strip()]
        hops = config.get_int('CHECKIN_PROXY_HOPS', 1, minimum=1)
        if forwarded:
            ip = forwarded[-min(hops, len(forwarded))]
    return ip


def _in_networks(ip, key):
    """Is ``ip`` in the CIDRs of setting ``key``? None when the setting is empty."""
    nets = config.get(key, '') or ''
    nets = [n.strip() for n in str(nets).split(',') if n.strip()]
    if not nets:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for n in nets:
        try:
            if addr in ipaddress.ip_network(n, strict=False):
                return True
        except ValueError:
            continue
    return False


MOBILE_RE = re.compile(r'Mobile|Android|iPhone|iPad', re.I)


DEVICES = ('pc', 'mobile', 'unknown')


def looks_mobile(user_agent):
    """A hint only: a phone or tablet is never the PC at the seat. Anyone can set a User-Agent."""
    return bool(MOBILE_RE.search(user_agent or ''))


def device_class(said, user_agent):
    """'pc', 'mobile' or 'unknown'. The page says what it sees (OS, touch, screen size, from the
    browser), the User-Agent backs it up. No network list to keep up to date: whether it really is a
    wired PC at the seat is what the switches say in the background (verify_pending)."""
    if said == 'mobile' or looks_mobile(user_agent):
        return 'mobile'
    return said if said in DEVICES else 'unknown'


def ip_allowed(ip):
    """May a check-in come from ``ip``? With CHECKIN_ALLOWED_NETWORKS set, only from those networks,
    so a request that didn't come through the front door (no address) is outside too."""
    if ip is None:
        return _in_networks('', 'CHECKIN_ALLOWED_NETWORKS') is None
    return _in_networks(ip, 'CHECKIN_ALLOWED_NETWORKS') is not False


def _same_pc(row, ip):
    """Is ``row`` this PC's check-in? Never without an address: two check-ins from outside the
    front door are not the same machine."""
    return ip is not None and (row or {}).get('ip') == ip


# ── seat PINs ──────────────────────────────────────────────────────────────────
# No 0/O, 1/I/L, 5/S, 8/B: read off a printed card and typed, they get mixed up.
PIN_ALPHABET = '2346789ACDEFGHJKMNPQRTUVWXYZ'
PIN_LENGTH = 5   # 17 million PINs: a guess hits one of 4000 seats about once in 4000 tries
# ...so a script would find a seat in seconds. Wrong PINs are counted per PC; past the limit it
# waits out the window. A typo or two is fine, guessing isn't.
WRONG_PIN_WINDOW = 600
_wrong_pins = {}          # ip -> [times of wrong PINs]


def _wrong_pin_wait(ip, now):
    """Seconds this PC must wait before it may try a PIN again, 0 when it may."""
    limit = config.get_int('CHECKIN_PIN_TRIES', 10, minimum=1)
    recent = [t for t in _wrong_pins.get(ip, []) if 0 <= now - t < WRONG_PIN_WINDOW]
    if recent:
        _wrong_pins[ip] = recent
    else:
        _wrong_pins.pop(ip, None)
    return int(recent[-limit] + WRONG_PIN_WINDOW - now) + 1 if len(recent) >= limit else 0


def _wrong_pin(ip, now):
    if len(_wrong_pins) > 10000:   # a flood of addresses must not grow this forever
        for key in [k for k, v in _wrong_pins.items() if not 0 <= now - v[-1] < WRONG_PIN_WINDOW]:
            del _wrong_pins[key]
    _wrong_pins.setdefault(ip, []).append(now)


def _beside_checkins(name):
    # Next to checkins.json, so they land in the same state folder (and volume).
    return os.path.join(os.path.dirname(_path()), name)


def _pins_path():
    configured = config.get('CHECKIN_PINS_FILE', '')
    if configured:
        from floorbit import store
        return store.event_file(configured)
    return _beside_checkins('checkin_pins.json')


def load_pins():
    """{seat: PIN} for the seats that have one."""
    from floorbit import store
    try:
        return store.read_json(_pins_path(), {}) or {}
    except json.JSONDecodeError:
        return {}


def ensure_pins(seats):
    """{seat: PIN} for ``seats``, giving a new random PIN to each seat that has none yet. Stored,
    so a reprint of the cards gives the same PINs, and unique, so the PIN alone names the seat."""
    with _lock:
        pins = load_pins()
        used = set(pins.values())
        added = False
        for seat in sorted(seats):
            if seat in pins:
                continue
            pin = ''.join(secrets.choice(PIN_ALPHABET) for _ in range(PIN_LENGTH))
            while pin in used:
                pin = ''.join(secrets.choice(PIN_ALPHABET) for _ in range(PIN_LENGTH))
            pins[seat] = pin
            used.add(pin)
            added = True
        if added:
            from floorbit import store
            store.write_json(_pins_path(), pins)
    return {s: pins[s] for s in seats}


def clean_pin(pin):
    return re.sub(r'[\s-]', '', str(pin or '')).upper()


def seat_for_pin(pin):
    """The seat whose card carries this PIN, or None."""
    given = clean_pin(pin)
    if not given:
        return None
    found = None
    for seat, known in load_pins().items():
        if hmac.compare_digest(given, known):   # constant time: the PIN is the only secret here
            found = seat
    return found


def seat_pin(seat):
    return load_pins().get(str(seat).strip().upper())


def pin_matches(seat, pin):
    return seat_for_pin(pin) == str(seat).strip().upper()


def normalise_seat(seat, known=None):
    """"c14" or "C 14" -> "C-14" when that is a seat on the plan; anything else as typed, upper case."""
    seat = re.sub(r'\s+', ' ', (seat or '').strip()).upper()
    if known and seat not in known:
        m = re.fullmatch(r'([A-Z]+)[ -]?(\d+)', seat)
        if m and f'{m[1]}-{int(m[2])}' in known:
            return f'{m[1]}-{int(m[2])}'
    return seat


def short_address():
    """CHECKIN_ADDRESS as a bare host name: "http://Checkin.LAN/" -> "checkin.lan"."""
    raw = str(config.get('CHECKIN_ADDRESS', '') or '').strip().lower()
    raw = re.sub(r'^[a-z]+://', '', raw)
    return raw.split('/')[0].split(':')[0]


def is_short_address(host):
    want = short_address()
    return bool(want) and str(host or '').lower().split(':')[0] == want


# ── which port a PC is on ──────────────────────────────────────────────────────
_port_cache = {}      # ip -> (time, {"switch", "port", "mac", "edge"} or None)
PORT_CACHE_SECONDS = 60
EDGE_PORT_MACS = 4


def cached_port(ip):
    """``port_of`` from the cache only. A miss is looked up in the background, at the set rate."""
    hit = _port_cache.get(ip) if ip else None
    if hit and time.time() - hit[0] < PORT_CACHE_SECONDS:
        return hit[1]
    if ip:
        with _warm_lock:      # the page's threads add while the verifier takes
            if len(_warm) < 10000:
                _warm.add(ip)
        _wake.set()
    return None


def port_of(ip):
    """The switch port an IP is plugged into, from the monitoring source (ARP and MAC tables).
    None when it doesn't know. Cached for a minute: the check-in page asks on every load."""
    if not ip:
        return None
    hit = _port_cache.get(ip)
    if hit and time.time() - hit[0] < PORT_CACHE_SECONDS:
        return hit[1]
    found, sure = None, True
    try:
        monitor = _monitoring()
        port = monitor.resolve_ip(ip) if monitor.enabled() else None
        if port and port.get('port'):
            found = {'switch': port.get('device_name') or port.get('hostname'), 'port': port.get('port'),
                     'mac': normalise_mac(port.get('mac')),
                     # More MACs than a PC (and its VMs) on the port: an AP, a desk switch, an uplink.
                     'edge': (port.get('macs_on_port') or 0) <= EDGE_PORT_MACS}
    except Exception:  # noqa: BLE001  # a slow or broken monitoring source must not stop a check-in
        found, sure = None, False
    from floorbit import sources
    if found or (sure and not sources.offline()):
        # Not "don't know" while the agent or LibreNMS is away: a check-in tried during an
        # outage would keep failing for a minute after it is back.
        _port_cache[ip] = (time.time(), found)
    return found


def _same_port(a, b):
    from floorbit.syslog import canonical_port
    return bool(a and b and str(a.get('switch') or '').lower() == str(b.get('switch') or '').lower()
                and canonical_port(a.get('port') or '') == canonical_port(b.get('port') or ''))


def _port_key(port):
    from floorbit.syslog import canonical_port
    return (str(port.get('switch') or '').lower(), canonical_port(port.get('port') or ''))


def planned_seat(port, load_data):
    """The seat the patch plan (cables.py) puts on this port, if any."""
    if not port:
        return None
    from floorbit import cables
    return cables.port_seats(load_data(), learned=False).get(_port_key(port))


# ── seat to switch port, learned from check-ins ───────────────────────────────
# What the event cares about in the end: which switch port each seat is on. A check-in with the
# seat's PIN proves the seat, the request's IP gives the port (core ARP, then the access switches'
# MAC tables), and that pair is kept here. The IP was only the way there: once the port is known,
# the seat shows whatever IP and MAC the port has now.
def _ports_path():
    configured = config.get('CHECKIN_PORTS_FILE', '')
    if configured:
        from floorbit import store
        return store.event_file(configured)
    return _beside_checkins('seat_ports.json')


def learned_ports():
    """{seat: {"switch", "port", "learned_at", "username"}}."""
    from floorbit import store
    try:
        return store.read_json(_ports_path(), {}) or {}
    except json.JSONDecodeError:
        return {}


def learn_port(seat, port, username, now=None, source='checkin'):
    """``source``: ``checkin`` (the attendee's own) or ``walk`` (the crew's walk-through,
    floorbit/seat_walk.py)."""
    from floorbit import store
    with _lock:
        rows = learned_ports()
        old = rows.get(seat)
        if old and _same_port(old, port) and old.get('source', 'checkin') == source:
            return old
        rows[seat] = {'switch': port['switch'], 'port': port['port'],
                      'learned_at': time.time() if now is None else now, 'username': username, 'source': source}
        store.write_json(_ports_path(), rows)
    events.publish('seat_ports.changed', {'seat': seat})
    return rows[seat]


def forget_port(seat):
    from floorbit import store
    with _lock:
        rows = learned_ports()
        if rows.pop(seat, None) is None:
            return False
        store.write_json(_ports_path(), rows)
    events.publish('seat_ports.changed', {'seat': seat})
    return True


def forget_all_ports():
    """Forget every learned seat port of the current event (one day after it ended). The count."""
    from floorbit import store
    with _lock:
        rows = learned_ports()
        if not rows:
            return 0
        store.write_json(_ports_path(), {})
    events.publish('seat_ports.changed', {})
    return len(rows)


def learned_port_seats():
    """{(switch lowercase, canonical port): seat} from check-ins; the newest wins a shared port."""
    out = {}
    for seat, row in sorted(learned_ports().items(), key=lambda kv: kv[1].get('learned_at') or 0):
        out[_port_key(row)] = seat
    return out


def port_conflicts(data):
    """Learned ports the crew should look at: one port learned for two seats, or a port the patch
    plan gives to another seat. [{"kind", "seat", "other", "switch", "port"}]."""
    from floorbit import cables
    planned = cables.port_seats(data, learned=False)
    by_port = {}
    for seat, row in learned_ports().items():
        by_port.setdefault(_port_key(row), []).append((seat, row))
    out = []
    for key, held in sorted(by_port.items()):
        seats = sorted(seat for seat, _row in held)
        row = held[0][1]
        if len(seats) > 1:
            out.append({'kind': 'shared', 'seat': seats[0], 'other': seats[1:], 'switch': row['switch'],
                        'port': row['port']})
        plan = planned.get(key)
        if plan and plan not in seats:
            out.append({'kind': 'plan', 'seat': seats[0], 'other': [plan], 'switch': row['switch'],
                        'port': row['port']})
    # A learned port outside the rough area the crew gave for it (floorbit/port_areas.py): a wrong
    # PIN or a card on the wrong seat. Only when no exact plan says anything about that port.
    from floorbit import port_areas
    areas = port_areas.all_areas(data)
    for seat, row in sorted(learned_ports().items()):
        area = port_areas.area_for(row['switch'], row['port'], areas)
        if area and seat not in area['seats'] and _port_key(row) not in planned:
            out.append({'kind': 'area', 'seat': seat, 'other': [area['label']], 'switch': row['switch'],
                        'port': row['port']})
    learned = learned_ports()
    for seat, row in sorted(load_all().items()):
        port = learned.get(seat) or row.get('port_seen')
        if row.get('taken_from') and port:
            out.append({'kind': 'taken', 'seat': seat, 'other': [], 'switch': port['switch'],
                        'port': port['port']})
    return out


def suggest_seat(ip, load_data, app=None):
    """The seat this PC is on, when Floorbit already knows it: its own check-in, the patch plan
    or an earlier check-in for its port. Shown on the check-in page as a hint, never required."""
    row = find_by_ip(ip)
    if row:
        return row['seat']
    finder = (app.extensions if app else {}).get('floorbit_port_clients')
    if finder is not None and ip in (finder.seat_ips or {}):
        return finder.seat_ips[ip]
    # Never wait for LibreNMS here: at doors-open a thousand pages load at once. A reload shows it.
    port = cached_port(ip)
    if not port:
        return None
    from floorbit import cables
    return cables.port_seats(load_data()).get(_port_key(port))


def known_seats(load_data):
    """Seat numbers from the floor plan's seat blocks, as the frontend numbers them."""
    from floorbit import incidents
    return incidents.seat_numbers(load_data())


# ── core ───────────────────────────────────────────────────────────────────────
class CheckinError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def check_in(seat, username, ip, load_data, mac=None, user_agent=None, pin=None, device=None, client=None):
    """Check in. With ``pin`` the seat comes from the PIN (the card at the seat) and whatever seat
    was typed is ignored; without it the seat is as typed (the phone page from the QR code).

    ``ip`` is the PC's address from the front door (attendee_ip), or None from outside it: then the
    seat and nick are kept, but nothing about a port. ``client`` keys the wrong-PIN lockout."""
    seats = known_seats(load_data)
    username = (username or '').strip()
    pin_ok = False
    # First, so that from outside the event network a PIN can't even be tested.
    if not ip_allowed(ip):
        raise CheckinError('Check in from your seat PC on the event network.', 403)
    mine = find_by_ip(ip)
    guard = ip or f'outside:{client or "?"}'     # whose wrong PINs count together
    if pin:
        with _lock:
            wait = _wrong_pin_wait(guard, time.time())
            if wait:
                minutes = (wait + 59) // 60
                raise CheckinError(f'Too many wrong PINs. Try again in {minutes} min or ask the crew.', 429)
            seat = seat_for_pin(pin)
            if seat is None:
                _wrong_pin(guard, time.time())
        if seat is None:
            raise CheckinError('That PIN is not on any seat card. Check the card at your seat.', 403)
        held = load_all().get(seat)
        # One use: once a PIN checked a seat in, only that PC may use it again (to change the nick).
        # Anyone else asks the crew, who remove the check-in and so open the PIN again.
        if held and held.get('pin_ok') and not _same_pc(held, ip):
            raise CheckinError('That PIN was already used. Ask the crew if this is your seat.', 409)
        pin_ok = True
    elif not seat and mine:
        # The PC that checked in changes its nick: no PIN needed, the seat stays.
        seat, pin_ok = mine['seat'], bool(mine.get('pin_ok'))
    else:
        seat = normalise_seat(seat, seats)
        if not seat:
            raise CheckinError('Enter the PIN from the card at your seat.')
        if not SEAT_RE.match(seat):
            # They typed a seat, not a PIN: say what a seat number looks like.
            raise CheckinError('Enter the seat number from your ticket, for example A-12.')
        held = load_all().get(seat)
        if held and held.get('pin_ok') and not _same_pc(held, ip):
            # The seat's card already checked it in: a typed number must not take it over.
            raise CheckinError(f'Seat {seat} was already checked in with its seat card. '
                               'Ask the crew if this is your seat.', 409)
    if not USER_RE.match(username):
        raise CheckinError('Enter a username (up to 48 characters).')
    if not pin and config.get_bool('CHECKIN_VALIDATE_SEATS', True) and seats and seat not in seats:
        raise CheckinError(f'Seat {seat} is not on the floor plan.')
    if not pin_ok and config.get_bool('CHECKIN_REQUIRE_PIN', False) and (mine or {}).get('seat') != seat:
        raise CheckinError('Enter the PIN from the card at your seat.', 403)

    # Nothing slow here: the portal answers at once. The MAC and the switch port are looked up in
    # the background (verify_pending), and only a wired PC on one access port teaches the seat.
    mac = normalise_mac(mac)
    device = device_class(device, user_agent)
    now = time.time()
    with _lock:
        rows = load_all()
        held = rows.get(seat)
        # Again under the lock: PCs typing the same card at the same moment all passed the check
        # above, and the last one took the seat from the others.
        if held and held.get('pin_ok') and not _same_pc(held, ip):
            if pin:
                raise CheckinError('That PIN was already used. Ask the crew if this is your seat.', 409)
            raise CheckinError(f'Seat {seat} was already checked in with its seat card. '
                               'Ask the crew if this is your seat.', 409)
        # One machine holds one seat: drop other seats with this IP or MAC
        moved_from = [s for s, r in rows.items()
                      if s != seat and (_same_pc(r, ip) or (mac and r.get('mac') == mac))]
        moved_rows = [rows.pop(s) for s in moved_from]
        prev = rows.get(seat, {})
        # Somebody else's seat, from another machine: kept (people do swap), shown to the crew.
        taken_over = (prev.get('username') and prev['username'] != username and not _same_pc(prev, ip)
                      and not (mac and prev.get('mac') == mac))
        row = {
            'seat': seat,
            'username': username,
            'ip': ip,
            'mac': mac or (prev.get('mac') if _same_pc(prev, ip) else None),
            'checked_in_at': prev.get('checked_in_at') if prev.get('username') == username else now,
            'last_seen': now,
            'ip_changed': None,
            'user_agent': (user_agent or '')[:200] or None,
            'pin_ok': pin_ok,
            'device': device,
            # pending: the background looks for the PC's switch port; verified: found on one access
            # port; not_wired: a phone or tablet, or from outside the front door (no address);
            # unverified: not found on one access port in time.
            # Only verified with a PIN teaches the seat its port.
            'wired': ('not_wired' if device == 'mobile' or ip is None else
                      prev['wired'] if _same_pc(prev, ip) and prev.get('wired') == 'verified' else 'pending'),
            'port_seen': prev.get('port_seen') if _same_pc(prev, ip) else None,
            'taken_from': ({'username': prev['username'], 'at': now} if taken_over
                           else prev.get('taken_from') if prev.get('username') == username else None),
        }
        if not row['mac']:   # the same machine moving seats keeps the MAC it was known by
            row['mac'] = next((r['mac'] for r in moved_rows if _same_pc(r, ip) and r.get('mac')), None)
        if row['checked_in_at'] is None:
            row['checked_in_at'] = now
        rows[seat] = row
        _save_all(rows)
        if pin_ok and row['wired'] == 'verified' and row['port_seen']:
            learn_port(seat, row['port_seen'], username, now=now)
        for old in moved_rows:
            history.record('moved', old, ts=now, to_seat=seat)
        history.record('checkin', row, ts=now)
    seat_sources.invalidate()
    events.publish('checkin', {'seat': seat, 'username': username, 'ip': ip,
                               'mac': row['mac'], 'moved_from': moved_from})
    from floorbit import checkin_lookup
    try:
        checkin_lookup.touch(now)
    except Exception as exc:  # noqa: BLE001  # the window is a convenience: the check-in stands
        print(f'[check-in] could not note the activity: {exc}')
    if row['wired'] == 'pending':
        _wake.set()
    return row


# ── wired or not, in the background ────────────────────────────────────────────
VERIFY_EVERY = 10          # seconds between tries while check-ins wait
VERIFY_GIVE_UP = 15 * 60   # LibreNMS polls ARP and MAC tables every few minutes: give it time
_wake = threading.Event()
_bucket = {'tokens': None, 'at': None}
_warm = set()              # IPs the check-in page asked about: their port is looked up when there's room
_warm_lock = threading.Lock()


def _budget(now, wanted):
    """Port lookups allowed this round, up to ``wanted``: CHECKIN_VERIFY_RATE a second, saved up
    to VERIFY_EVERY seconds' worth, taken from the bucket."""
    rate = config.get_int('CHECKIN_VERIFY_RATE', 10, minimum=1)
    cap = rate * VERIFY_EVERY
    tokens, at = _bucket['tokens'], _bucket['at']
    tokens = cap if tokens is None else min(cap, tokens + max(0, now - at) * rate)
    allowed = min(int(tokens), wanted)
    _bucket.update(tokens=tokens - allowed, at=now)
    return allowed


def queue_depth():
    """Check-ins waiting for their port lookup."""
    return sum(1 for r in load_all().values() if r.get('wired') == 'pending')


def verify_pending(now=None):
    """Look up the switch port of each check-in that waits for it. Found on one access port:
    ``verified``, and with a PIN the seat learns that port. Returns the seats that changed."""
    now = time.time() if now is None else now
    everyone = load_all()
    pending = {s: r for s, r in everyone.items() if r.get('wired') == 'pending'}
    found = {}
    # Oldest first, and only as many as the rate allows: a burst at doors-open waits its turn
    # instead of sending LibreNMS a thousand lookups at once. The rest come next round.
    queue = sorted(pending.items(), key=lambda kv: kv[1].get('checked_in_at') or 0)
    for seat, row in queue[:_budget(now, len(queue))]:
        port = port_of(row.get('ip'))
        mac = row.get('mac') or (port or {}).get('mac') or lookup_mac(row.get('ip'))
        asked = None
        if not (port and port.get('edge')) and row.get('ip'):
            # The tables don't know it yet: ask the switches for this one PC (docs/segments.md).
            asked = _ask_switches(row['ip'], seat, mac, now)
            if asked.get('state') == 'found':
                port = {'switch': asked['switch'], 'port': asked['port'], 'edge': True}
                mac = mac or asked.get('mac')
        if port and port.get('edge'):
            found[seat] = ('verified', {'switch': port['switch'], 'port': port['port']}, mac, asked)
        elif now - (row.get('checked_in_at') or now) > VERIFY_GIVE_UP:
            found[seat] = ('unverified', None, mac, asked)
        elif (mac and not row.get('mac')) or _lookup_news(row, asked):
            found[seat] = ('pending', None, mac, asked)
    # What's left of the budget warms the cache for the check-in page's seat hint. A PC that has
    # checked in meanwhile needs no hint.
    with _warm_lock:
        _warm.difference_update(r.get('ip') for r in everyone.values())
        take = list(_warm)[:_budget(now, len(_warm))]
        _warm.difference_update(take)
    for ip in take:
        port_of(ip)
    if not found:
        return []
    changed = []
    with _lock:
        rows = load_all()
        for seat, (state, port, mac, asked) in found.items():
            row = rows.get(seat)
            if not row or row.get('wired') != 'pending' or row.get('ip') != pending[seat].get('ip'):
                continue    # checked in again meanwhile: that one has its own turn
            if mac and not row.get('mac'):
                row['mac'] = mac
                history.record('mac_found', row, ts=now)
            row['wired'] = state
            if asked:
                row['lookup'] = {k: asked[k] for k in ('state', 'todo', 'vlan') if asked.get(k) is not None}
            if port:
                row.update(port_seen=port, verified_at=now)
            changed.append(seat)
        if changed:
            _save_all(rows)
    for seat in changed:
        row = rows[seat]
        if row['wired'] == 'verified' and row.get('pin_ok'):
            learn_port(seat, row['port_seen'], row['username'], now=now)
    if changed:
        seat_sources.invalidate()
        events.publish('checkin.verified', {'seats': changed})
    return changed


def _ask_switches(ip, seat, mac, now):
    """floorbit/checkin_lookup.py, never failing the round: {state, ...}."""
    from floorbit import checkin_lookup
    try:
        return checkin_lookup.lookup(ip, seat=seat, mac=mac, now=now)
    except Exception as exc:  # noqa: BLE001  # one broken lookup must not stop the others
        print(f'[check-in] switch lookup for {seat} failed: {exc}')
        return {'state': 'error'}


def _lookup_news(row, asked):
    """The lookup says something new for the crew (a to-do, closed, an error)."""
    if not asked:
        return False
    said = {k: asked[k] for k in ('state', 'todo', 'vlan') if asked.get(k) is not None}
    return said != (row.get('lookup') or {})


def retry(seat):
    """Look for the seat's port again (crew): back to pending, and the background starts now."""
    with _lock:
        rows = load_all()
        row = rows.get(str(seat).upper())
        if not row:
            return None
        row.update(wired='pending', checked_in_at=time.time() if row.get('wired') == 'unverified'
                   else row.get('checked_in_at'))
        _port_cache.pop(row.get('ip'), None)
        _save_all(rows)
    _wake.set()
    return row


WIRED_STATES = ('pending', 'verified', 'not_wired', 'unverified')


def overview(load_data):
    """The crew's Check-in page: counts, every check-in with its state, the review list."""
    rows = sorted(load_all().values(), key=lambda r: -(r.get('checked_in_at') or 0))
    learned = learned_ports()
    pins = load_pins()
    used = {r['seat'] for r in rows if r.get('pin_ok')}
    data = load_data()
    conflicts = port_conflicts(data)
    counts = {state: sum(1 for r in rows if r.get('wired', 'pending') == state) for state in WIRED_STATES}
    counts.update(checked_in=len(rows), conflicts=len(conflicts), learned=len(learned),
                  unused_pins=len([s for s in pins if s not in used]), pins=len(pins))
    from floorbit import port_areas
    areas = port_areas.all_areas(data)
    out = []
    for r in rows:
        seen = r.get('port_seen')
        out.append({'area': port_areas.hint(seen['switch'], seen['port'], areas) if seen else None,
                    'seat': r['seat'], 'username': r.get('username'), 'ip': r.get('ip'), 'mac': r.get('mac'),
                    'device': r.get('device') or 'unknown', 'wired': r.get('wired') or 'pending',
                    'port': r.get('port_seen'), 'learned': learned.get(r['seat']), 'pin': bool(r.get('pin_ok')),
                    'checked_in_at': r.get('checked_in_at'), 'verified_at': r.get('verified_at'),
                    'lookup': r.get('lookup')})
    from floorbit import checkin_lookup, segments
    lookups = {**checkin_lookup.window(data=data),
               'segments_on': sum(1 for s in segments.all_segments() if s.get('lookups'))}
    return {'counts': counts, 'rows': out, 'conflicts': conflicts, 'lookups': lookups}


class CheckinVerifier:
    """Runs ``verify_pending`` while check-ins wait, woken at once by a new one."""

    def __init__(self):
        self._thread = None
        self._lock = threading.Lock()
        self.last_error = None

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name='checkin-verify', daemon=True)
            self._thread.start()

    def _run(self):
        wait = VERIFY_EVERY
        while True:
            _wake.wait(wait)
            _wake.clear()
            wait = VERIFY_EVERY
            try:
                if config.get_bool('CHECKIN_ENABLED', False) and _monitoring().enabled():
                    verify_pending()
                    if queue_depth() or _warm:
                        wait = 1      # a burst drains at the rate, not one batch per VERIFY_EVERY
                    self.last_error = None
            except Exception as exc:  # noqa: BLE001  # keep the thread alive, try again next round
                self.last_error = str(exc)
                print(f'[integrations] check-in verification failed: {exc}')


def remove(seat):
    with _lock:
        rows = load_all()
        row = rows.pop(seat.upper(), None)
        if row:
            _save_all(rows)
            history.record('removed', row)
    if row:
        seat_sources.invalidate()
        events.publish('checkin.removed', {'seat': seat.upper()})
    return row


def find_by_ip(ip, seat=None):
    """This IP's check-in (on ``seat``, when given)."""
    if not ip:
        return None
    for row in load_all().values():
        if row.get('ip') == ip and (seat is None or row['seat'] == seat):
            return row
    return None


def refresh_once():
    """Follow DHCP changes: fill missing MACs, move IPs that changed for a known MAC."""
    changed, logged = [], []
    with _lock:
        rows = load_all()
        for seat, row in rows.items():
            if not row.get('ip'):
                continue      # checked in from outside the front door: no PC to follow
            if not row.get('mac'):
                mac = lookup_mac(row['ip'])
                if mac:
                    row['mac'] = mac
                    changed.append(seat)
                    logged.append(('mac_found', row, {}))
                continue
            current = lookup_ip(row['mac'])
            if current and current != row['ip']:
                logged.append(('ip_changed', row, {'previous_ip': row['ip']}))
                row['ip'] = current
                row['ip_changed'] = time.time()
                changed.append(seat)
        if changed:
            _save_all(rows)
            for kind, row, extra in logged:
                history.record(kind, row, **extra)
    if changed:
        seat_sources.invalidate()
        events.publish('checkin.refreshed', {'seats': changed})
    return changed


class CheckinRefresher:
    def __init__(self):
        self._thread = None
        self._lock = threading.Lock()
        self.last_run = None
        self.last_error = None

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name='checkin-refresh', daemon=True)
            self._thread.start()

    def _run(self):
        while True:
            interval = config.get_int('CHECKIN_REFRESH_INTERVAL', 300, minimum=30)
            try:
                if _monitoring().enabled() and config.get_bool('CHECKIN_ENABLED', False) and load_all():
                    refresh_once()
                    self.last_run, self.last_error = time.time(), None
            except Exception as exc:  # noqa: BLE001  # keep the refresh thread alive
                self.last_error = str(exc)
                print(f"[integrations] check-in refresh failed: {exc}")
            time.sleep(interval)


# ── seat source ─────────────────────────────────────────────────────────────────
@seat_sources.register
class CheckinSource(seat_sources.SeatSource):
    name = 'checkin'
    label = 'Seat check-in page'

    def configured(self):
        return config.get_bool('CHECKIN_ENABLED', False)

    def fetch(self):
        return {seat: {'username': r.get('username'), 'ip_address': r.get('ip'),
                       'mac_address': r.get('mac'), 'checked_in_at': r.get('checked_in_at')}
                for seat, r in load_all().items()}
