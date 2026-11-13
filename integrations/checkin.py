"""Seat check-in: people tell us their seat, we record their IP and MAC.

A small page at ``/checkin`` asks for seat number and username. The server
takes the request's source IP, looks up the MAC for that IP in LibreNMS' ARP
data, and stores one row per seat:

    seat, username, ip, mac, checked_in_at, last_seen, ip_changed

This is exposed as the ``checkin`` seat source, so ``SEAT_SOURCES=checkin,json``
puts check-ins in front of the static file.

Things that make an IP wrong, and what this does about them:

* NAT / proxies: if the app sits behind a reverse proxy, set
  ``CHECKIN_TRUST_PROXY=true`` so ``X-Forwarded-For`` is used. If players are
  behind NAT the IP is the router's and nothing can fix that, so
  ``CHECKIN_ALLOWED_NETWORKS`` (CIDRs, e.g. ``10.0.0.0/16``) rejects check-ins
  from outside the player networks instead of storing a useless IP.
* DHCP leases: the MAC is treated as the stable identity. A background refresh
  (``CHECKIN_REFRESH_INTERVAL``) asks LibreNMS which IP that MAC has now and
  updates the row; ``ip_changed`` records when that happened.
* One machine, one seat: checking in from an IP or MAC that already holds
  another seat moves it.
"""
import ipaddress
import json
import os
import re
import tempfile
import threading
import time

import requests
from flask import request

from . import config, events, history, seat_sources

_lock = threading.RLock()
SEAT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _\-]{0,15}$')
USER_RE = re.compile(r'^[^\x00-\x1f<>]{1,48}$')


def _path():
    return config.get('CHECKIN_FILE', 'checkins.json')


def load_all():
    with _lock:
        try:
            with open(_path()) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


def _save_all(rows):
    path = _path()
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix='.checkins-')
    with os.fdopen(fd, 'w') as f:
        json.dump(rows, f, indent=2)
    os.replace(tmp, path)   # atomic: a crash never leaves half a file


# ── LibreNMS lookups ─────────────────────────────────────────────────────────
def _librenms():
    url = (config.get('LIBRENMS_URL', '') or '').rstrip('/')
    token = config.get('LIBRENMS_TOKEN', '') or ''
    return url, token, config.get_bool('LIBRENMS_VERIFY_SSL', True)


def normalise_mac(mac):
    if not mac:
        return None
    hexchars = re.sub(r'[^0-9a-fA-F]', '', str(mac)).lower()
    if len(hexchars) != 12:
        return None
    return ':'.join(hexchars[i:i + 2] for i in range(0, 12, 2))


def _arp_query(query):
    url, token, verify = _librenms()
    if not (url and token):
        return []
    resp = requests.get(f'{url}/api/v0/resources/ip/arp/{query}',
                        headers={'X-Auth-Token': token, 'Accept': 'application/json'},
                        timeout=10, verify=verify)
    if not resp.ok:
        return []
    return resp.json().get('arp', []) or []


def lookup_mac(ip):
    """IP → MAC from LibreNMS ARP data (None if unknown)."""
    try:
        for entry in _arp_query(ip):
            if entry.get('ipv4_address') == ip:
                return normalise_mac(entry.get('mac_address'))
    except requests.RequestException as exc:
        print(f"[integrations] check-in MAC lookup failed for {ip}: {exc}")
    return None


def lookup_ip(mac):
    """MAC → current IP from LibreNMS ARP data (None if unknown)."""
    try:
        want = normalise_mac(mac)
        for entry in _arp_query(want):
            if normalise_mac(entry.get('mac_address')) == want and entry.get('ipv4_address'):
                return entry['ipv4_address']
    except requests.RequestException as exc:
        print(f"[integrations] check-in IP lookup failed for {mac}: {exc}")
    return None


# ── request helpers ──────────────────────────────────────────────────────────
def client_ip():
    ip = request.remote_addr or ''
    if config.get_bool('CHECKIN_TRUST_PROXY', False):
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            ip = forwarded.split(',')[0].strip()
    return ip


def ip_allowed(ip):
    nets = config.get('CHECKIN_ALLOWED_NETWORKS', '') or ''
    nets = [n.strip() for n in str(nets).split(',') if n.strip()]
    if not nets:
        return True
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


def check_in(seat, username, ip, load_data, mac=None, user_agent=None):
    seat = (seat or '').strip().upper()
    username = (username or '').strip()
    if not SEAT_RE.match(seat):
        raise CheckinError('Enter a seat number like A-12.')
    if not USER_RE.match(username):
        raise CheckinError('Enter a username (up to 48 characters).')
    if not ip_allowed(ip):
        raise CheckinError('Check in from your seat PC on the event network.', 403)
    if config.get_bool('CHECKIN_VALIDATE_SEATS', True):
        seats = known_seats(load_data)
        if seats and seat not in seats:
            raise CheckinError(f'Seat {seat} is not on the floor plan.')

    mac = normalise_mac(mac) or lookup_mac(ip)
    now = time.time()
    with _lock:
        rows = load_all()
        # One machine holds one seat: drop other seats with this IP or MAC
        moved_from = [s for s, r in rows.items()
                      if s != seat and (r.get('ip') == ip or (mac and r.get('mac') == mac))]
        moved_rows = [rows.pop(s) for s in moved_from]
        prev = rows.get(seat, {})
        row = {
            'seat': seat,
            'username': username,
            'ip': ip,
            'mac': mac or (prev.get('mac') if prev.get('ip') == ip else None),
            'checked_in_at': prev.get('checked_in_at') if prev.get('username') == username else now,
            'last_seen': now,
            'ip_changed': None,
            'user_agent': (user_agent or '')[:200] or None,
        }
        if row['checked_in_at'] is None:
            row['checked_in_at'] = now
        rows[seat] = row
        _save_all(rows)
        for old in moved_rows:
            history.record('moved', old, ts=now, to_seat=seat)
        history.record('checkin', row, ts=now)
    seat_sources.invalidate()
    events.publish('checkin', {'seat': seat, 'username': username, 'ip': ip,
                               'mac': row['mac'], 'moved_from': moved_from})
    return row


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


def find_by_ip(ip):
    for row in load_all().values():
        if row.get('ip') == ip:
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
            url, token, _ = _librenms()
            if url and token and config.get_bool('CHECKIN_ENABLED', False) and load_all():
                try:
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
