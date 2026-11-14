"""Port actions (issues #16, #29): bounce a seat's switch port, or shut it for a security finding.
See docs/ports.md.

Floorbit never talks to a switch itself: a plugin with ``uses: [ports]`` does (the built-in SSH
port actions plugin, or the demo data). When that plugin says it needs a login, the tech types
their own switch username and password for each action. It is used for that one connection and
then dropped: never stored, logged, cached or sent anywhere else.

The switch and port come from Floorbit, never from the browser as free text: a seat is resolved
through the seat mapping and the monitoring source, and the switch must be in the inventory with
a management IP. Every attempt, failed ones too, goes to the audit log.
"""
import re
import threading
import time

from . import inventory, sources
from .plugins import PluginError
from .store import load_data

# Interface names as switches print them: Gi1/0/3, ethernet1/1/12, 1/1/5, xe-0/0/1.0, A12, Port-channel1.
PORT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/._:-]{0,47}$')
USER_RE = re.compile(r'^[^\s\x00-\x1f]{1,64}$')
COOLDOWN = 30            # seconds before the same port can be bounced again
LOGIN_FAILURES = 5       # failed switch logins per account ...
LOGIN_WINDOW = 900       # ... in this many seconds, then a pause

_lock = threading.Lock()
_busy = set()            # switches with an action running: one at a time per switch
_last = {}               # (switch, port) -> time of the last bounce
_failures = {}           # username -> [times of failed switch logins]


class PortError(ValueError):
    def __init__(self, message, status=400, match_seat=None):
        super().__init__(message)
        self.status = status
        self.match_seat = match_seat   # the zone, when a match seat still needs its second confirmation


def plugin(registry):
    """The port actions plugin in use: the first one that is on, demo data first (or None)."""
    found = registry.feeders('ports')
    found.sort(key=lambda spec: spec.id != 'demo')
    return found[0] if found else None


def info(registry):
    spec = plugin(registry)
    if not spec:
        return {'available': False, 'needs_login': False, 'plugin': None}
    try:
        needs_login = bool(registry.call(spec, 'port_login'))
    except PluginError:
        needs_login = True
    return {'available': True, 'needs_login': needs_login, 'plugin': spec.name}


def _switch(data, name):
    short = str(name or '').lower().split('.')[0]
    dev = next((d for d in inventory.devices(data, include_hidden=True)
                if d['name'].lower().split('.')[0] == short and short), None)
    if not dev:
        raise PortError(f'{name} is not in the inventory, so Floorbit has no address for it.')
    if not dev.get('mgmt_ip'):
        raise PortError(f'{dev["name"]} has no management IP in the inventory.')
    return dev


def resolve_seat(seat):
    """(switch name, port) for a seat, from the seat mapping and the monitoring source."""
    from integrations import seat_sources
    mapping = (seat_sources.load() or {}).get(seat) or {}
    ip = mapping.get('ip_address')
    if not ip and mapping.get('mac'):
        ip = sources.monitoring().ip_for_mac(mapping['mac'])
    if not ip:
        raise PortError(f'Seat {seat} has no IP or MAC in the seat mapping.')
    found = sources.monitoring().resolve_ip(ip) or {}
    if not found.get('device_name') or not found.get('port'):
        raise PortError(f'Seat {seat} was not found on any switch port.')
    return found['device_name'], found['port']


def target(body):
    """The switch (inventory entry) and port the request is about."""
    seat = str(body.get('seat') or '').strip().upper()
    if body.get('finding'):
        # A security finding names its own switch and port: the browser only says which finding.
        from . import security
        found = security.get(str(body['finding']))
        if not found or not found.get('switch') or not found.get('port'):
            raise PortError('That finding has no switch port Floorbit can act on.')
        name, port, seat = found['switch'], found['port'], found.get('seat') or ''
    elif seat:
        name, port = resolve_seat(seat)
    else:
        name, port = body.get('switch'), body.get('port')
    port = str(port or '').strip()
    if not PORT_RE.match(port):
        raise PortError('That is not a port name Floorbit will send to a switch.')
    return _switch(load_data(), name), port, seat or None


def _login(body, needs_login):
    if not needs_login:
        return None
    username, password = body.get('username'), body.get('password')
    if not isinstance(username, str) or not USER_RE.match(username):
        raise PortError('Type your switch username.')
    if not isinstance(password, str) or not password or len(password) > 256 or '\n' in password:
        raise PortError('Type your switch password.')
    return {'username': username, 'password': password}


def _check_failures(account, now):
    recent = [t for t in _failures.get(account, []) if now - t < LOGIN_WINDOW]
    _failures[account] = recent
    if len(recent) >= LOGIN_FAILURES:
        raise PortError('Too many failed switch logins. Wait a few minutes before trying again.', 429)


ACTIONS = {
    # action: (plugin method, extra target keys, audit text, default message)
    'bounce': ('bounce_port', {}, 'Bounced port', '{port} on {switch} went down and came back up.'),
    'shutdown': ('set_port', {'enabled': False}, 'Shut port', '{port} on {switch} is shut until someone turns it on.'),
    'enable': ('set_port', {'enabled': True}, 'Turned port on', '{port} on {switch} is on again.'),
}


def act(registry, account, body, action):
    """Run one port action. Returns (switch, port, seat, message)."""
    method, extra, _label, default = ACTIONS[action]
    spec = plugin(registry)
    if not spec:
        raise PortError('No port actions plugin is on. An admin turns one on under Settings > Plugins.', 409)
    dev, port, seat = target(body)
    if seat and body.get('confirm_match') is not True:
        from .tournament import zone_of
        zone = zone_of(seat)
        if zone:
            # Tournament seats (issue #31): a bounced port can lose a match, so ask twice.
            raise PortError(f'Seat {seat} is a match seat ({zone}). Confirm again to {action} its port.', 409,
                            match_seat=zone)
    needs_login = info(registry)['needs_login']
    login = _login(body, needs_login)
    key = (dev['name'], port)
    now = time.time()
    with _lock:
        _check_failures(account, now)
        if action == 'bounce' and now - _last.get(key, 0) < COOLDOWN:
            raise PortError(f'{port} on {dev["name"]} was just bounced. Give it {COOLDOWN} seconds.', 429)
        if dev['name'] in _busy:
            raise PortError(f'Another port action on {dev["name"]} is still running.', 409)
        _busy.add(dev['name'])
    try:
        result = registry.call(spec, method, {
            'switch': dev['name'], 'host': dev['mgmt_ip'], 'port': port, 'model': dev.get('model') or '',
            'login': login, **extra})
    except PluginError as exc:
        if needs_login and 'login' in str(exc).lower():
            with _lock:
                _failures.setdefault(account, []).append(time.time())
        raise PortError(str(exc), 502) from None
    finally:
        if login:
            login.clear()   # drop the password as soon as the connection is done
        body.pop('password', None)
        with _lock:
            _busy.discard(dev['name'])
    with _lock:
        if action == 'bounce':
            _last[key] = time.time()
        _failures.pop(account, None)
    if action != 'bounce':
        _remember(dev['name'], port, seat, account, body.get('reason'), shut=action == 'shutdown')
    message = (result or {}).get('message') if isinstance(result, dict) else None
    return dev['name'], port, seat, str(message or default.format(port=port, switch=dev['name']))[:200]


def bounce(registry, account, body):
    return act(registry, account, body, 'bounce')


# ── Ports Floorbit shut, so nobody forgets to turn them on again ──────────────────────────
def _remember(switch, port, seat, account, reason, shut):
    from .store import save_data
    with _lock:
        data = load_data()
        kept = [p for p in data.get('ports_shut') or [] if (p.get('switch'), p.get('port')) != (switch, port)]
        if shut:
            kept.append({'switch': switch, 'port': port, 'seat': seat, 'by': account, 'at': time.time(),
                         'reason': ' '.join(str(reason or '').split())[:200]})
        data['ports_shut'] = kept[-500:]
        save_data(data)


def shut_ports():
    return list(load_data().get('ports_shut') or [])
