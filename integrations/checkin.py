"""Seat check-in: people tell us their seat, we record their IP and MAC.

A small page at ``/checkin`` asks for seat number and username. The server
takes the request's source IP, looks up the MAC for that IP in LibreNMS' ARP
data, and stores one row per seat:

    seat, username, ip, mac, checked_in_at, last_seen, ip_changed

This is exposed as the ``checkin`` seat source, so ``SEAT_SOURCES=checkin,json``
puts check-ins in front of the static file.

Things that make an IP wrong, and what this does about them:

* NAT / proxies: if the app sits behind a reverse proxy, set
  ``CHECKIN_TRUST_PROXY=true`` so ``X-Forwarded-For`` is used (the entry the
  proxy added, ``CHECKIN_PROXY_HOPS`` from the right). If players are
  behind NAT the IP is the router's and nothing can fix that, so
  ``CHECKIN_ALLOWED_NETWORKS`` (CIDRs, e.g. ``10.0.0.0/16``) rejects check-ins
  from outside the player networks instead of storing a useless IP.
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
import tempfile
import threading
import time

from flask import request

from . import config, events, history, seat_sources

_lock = threading.RLock()
SEAT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _\-]{0,15}$')
USER_RE = re.compile(r'^[^\x00-\x1f<>]{1,48}$')


def _path():
    return config.get('CHECKIN_FILE', 'checkins.json')


def load_all():
    with _lock:
        from floorbit import store
        try:
            return store.read_json(_path(), {})
        except json.JSONDecodeError:
            return {}


def _save_all(rows):
    from floorbit import database, store
    path = _path()
    if database.backend().kind != 'files':
        store.write_json(path, rows)
        return
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix='.checkins-')
    # One line, written whole: json.dump with indent encodes in pure Python, 30 ms a save at
    # 4000 seats (scripts/load_test.py), and every check-in saves.
    text = json.dumps(rows, separators=(',', ':'))
    with os.fdopen(fd, 'w') as f:
        f.write(text)
    os.replace(tmp, path)   # atomic: a crash never leaves half a file


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
def client_ip():
    ip = request.remote_addr or ''
    if config.get_bool('CHECKIN_TRUST_PROXY', False):
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
    return _in_networks(ip, 'CHECKIN_ALLOWED_NETWORKS') is not False


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
    recent = [t for t in _wrong_pins.get(ip, []) if now - t < WRONG_PIN_WINDOW]
    if recent:
        _wrong_pins[ip] = recent
    else:
        _wrong_pins.pop(ip, None)
    return int(recent[-limit] + WRONG_PIN_WINDOW - now) + 1 if len(recent) >= limit else 0


def _wrong_pin(ip, now):
    if len(_wrong_pins) > 10000:   # a flood of addresses must not grow this forever
        for key in [k for k, v in _wrong_pins.items() if now - v[-1] >= WRONG_PIN_WINDOW]:
            del _wrong_pins[key]
    _wrong_pins.setdefault(ip, []).append(now)


def _beside_checkins(name):
    # Next to checkins.json, so they land in the same state folder (and volume).
    return os.path.join(os.path.dirname(_path()), name)


def _pins_path():
    return config.get('CHECKIN_PINS_FILE', '') or _beside_checkins('checkin_pins.json')


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
    found = None
    try:
        monitor = _monitoring()
        port = monitor.resolve_ip(ip) if monitor.enabled() else None
        if port and port.get('port'):
            found = {'switch': port.get('device_name') or port.get('hostname'), 'port': port.get('port'),
                     'mac': normalise_mac(port.get('mac')),
                     # More MACs than a PC (and its VMs) on the port: an AP, a desk switch, an uplink.
                     'edge': (port.get('macs_on_port') or 0) <= EDGE_PORT_MACS}
    except Exception:  # noqa: BLE001  # a slow or broken monitoring source must not stop a check-in
        found = None
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
    return config.get('CHECKIN_PORTS_FILE', '') or _beside_checkins('seat_ports.json')


def learned_ports():
    """{seat: {"switch", "port", "learned_at", "username"}}."""
    from floorbit import store
    try:
        return store.read_json(_ports_path(), {}) or {}
    except json.JSONDecodeError:
        return {}


def learn_port(seat, port, username, now=None):
    from floorbit import store
    with _lock:
        rows = learned_ports()
        old = rows.get(seat)
        if old and _same_port(old, port):
            return old
        rows[seat] = {'switch': port['switch'], 'port': port['port'],
                      'learned_at': time.time() if now is None else now, 'username': username}
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
    seats = set()
    for block in load_data().get('seat_blocks', []):
        prefix = f"{block['name'].upper()}-" if block.get('name') else ''
        total = int(block.get('cols', 1)) * int(block.get('rows', 1))
        seats.update(f'{prefix}{i}' for i in range(1, total + 1))
    return seats


# ── core ───────────────────────────────────────────────────────────────────────
class CheckinError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def check_in(seat, username, ip, load_data, mac=None, user_agent=None, pin=None, device=None):
    """Check in. With ``pin`` the seat comes from the PIN (the card at the seat) and whatever seat
    was typed is ignored; without it the seat is as typed (the phone page from the QR code)."""
    seats = known_seats(load_data)
    username = (username or '').strip()
    pin_ok = False
    # First, so that from outside the event network a PIN can't even be tested.
    if not ip_allowed(ip):
        raise CheckinError('Check in from your seat PC on the event network.', 403)
    mine = find_by_ip(ip)
    if pin:
        with _lock:
            wait = _wrong_pin_wait(ip, time.time())
            if wait:
                minutes = (wait + 59) // 60
                raise CheckinError(f'Too many wrong PINs. Try again in {minutes} min or ask the crew.', 429)
            seat = seat_for_pin(pin)
            if seat is None:
                _wrong_pin(ip, time.time())
        if seat is None:
            raise CheckinError('That PIN is not on any seat card. Check the card at your seat.', 403)
        held = load_all().get(seat)
        # One use: once a PIN checked a seat in, only that PC may use it again (to change the nick).
        # Anyone else asks the crew, who remove the check-in and so open the PIN again.
        if held and held.get('pin_ok') and held.get('ip') != ip:
            raise CheckinError('That PIN was already used. Ask the crew if this is your seat.', 409)
        pin_ok = True
    elif not seat and mine:
        # The PC that checked in changes its nick: no PIN needed, the seat stays.
        seat, pin_ok = mine['seat'], bool(mine.get('pin_ok'))
    else:
        seat = normalise_seat(seat, seats)
        if not SEAT_RE.match(seat):
            raise CheckinError('Enter the PIN from the card at your seat.')
        held = load_all().get(seat)
        if held and held.get('pin_ok') and held.get('ip') != ip:
            # The seat's card already checked it in: a typed number must not take it over.
            raise CheckinError('That PIN was already used. Ask the crew if this is your seat.', 409)
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
        # One machine holds one seat: drop other seats with this IP or MAC
        moved_from = [s for s, r in rows.items()
                      if s != seat and (r.get('ip') == ip or (mac and r.get('mac') == mac))]
        moved_rows = [rows.pop(s) for s in moved_from]
        prev = rows.get(seat, {})
        # Somebody else's seat, from another machine: kept (people do swap), shown to the crew.
        taken_over = (prev.get('username') and prev['username'] != username and prev.get('ip') != ip
                      and not (mac and prev.get('mac') == mac))
        row = {
            'seat': seat,
            'username': username,
            'ip': ip,
            'mac': mac or (prev.get('mac') if prev.get('ip') == ip else None),
            'checked_in_at': prev.get('checked_in_at') if prev.get('username') == username else now,
            'last_seen': now,
            'ip_changed': None,
            'user_agent': (user_agent or '')[:200] or None,
            'pin_ok': pin_ok,
            'device': device,
            # pending: the background looks for the PC's switch port; verified: found on one access
            # port; not_wired: a phone or tablet; unverified: not found on one access port in time.
            # Only verified with a PIN teaches the seat its port.
            'wired': ('not_wired' if device == 'mobile' else
                      prev['wired'] if prev.get('ip') == ip and prev.get('wired') == 'verified' else 'pending'),
            'port_seen': prev.get('port_seen') if prev.get('ip') == ip else None,
            'taken_from': ({'username': prev['username'], 'at': now} if taken_over
                           else prev.get('taken_from') if prev.get('username') == username else None),
        }
        if not row['mac']:   # the same machine moving seats keeps the MAC it was known by
            row['mac'] = next((r['mac'] for r in moved_rows if r.get('ip') == ip and r.get('mac')), None)
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
        if port and port.get('edge'):
            found[seat] = ('verified', {'switch': port['switch'], 'port': port['port']}, mac)
        elif now - (row.get('checked_in_at') or now) > VERIFY_GIVE_UP:
            found[seat] = ('unverified', None, mac)
        elif mac and not row.get('mac'):
            found[seat] = ('pending', None, mac)
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
        for seat, (state, port, mac) in found.items():
            row = rows.get(seat)
            if not row or row.get('wired') != 'pending' or row.get('ip') != pending[seat].get('ip'):
                continue    # checked in again meanwhile: that one has its own turn
            if mac and not row.get('mac'):
                row['mac'] = mac
                history.record('mac_found', row, ts=now)
            row['wired'] = state
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
    conflicts = port_conflicts(load_data())
    counts = {state: sum(1 for r in rows if r.get('wired', 'pending') == state) for state in WIRED_STATES}
    counts.update(checked_in=len(rows), conflicts=len(conflicts), learned=len(learned),
                  unused_pins=len([s for s in pins if s not in used]), pins=len(pins))
    out = []
    for r in rows:
        out.append({'seat': r['seat'], 'username': r.get('username'), 'ip': r.get('ip'), 'mac': r.get('mac'),
                    'device': r.get('device') or 'unknown', 'wired': r.get('wired') or 'pending',
                    'port': r.get('port_seen'), 'learned': learned.get(r['seat']), 'pin': bool(r.get('pin_ok')),
                    'checked_in_at': r.get('checked_in_at'), 'verified_at': r.get('verified_at')})
    return {'counts': counts, 'rows': out, 'conflicts': conflicts}


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
