"""Why a device sends nothing: Telegraf's error lines and the API pollers' errors, per device and
collection type, sorted into a few kinds a tech can act on (docs/telemetry.md, "When a device
sends nothing").

Telegraf logs a failed gather as, for example::

    2026-11-19T08:18:30Z E! [inputs.snmp::sw-01] Error in plugin: agent udp://192.0.2.21:161:
        performing get on field sysName: ... recvfrom: connection refused

Floorbit's config names every input after its device (``alias``), so the line says which device
it is about without guessing from addresses.
"""
import re
import threading
import time

# A problem not seen again for this long is over: Telegraf repeats a failing gather every
# interval (30 to 60 s), gNMI redials every 10 s.
FORGET_AFTER = 180

# Telegraf's plugin names, as the Telemetry page's collection types call them.
DRIVER_OF = {'snmp': 'snmp', 'snmp_trap': 'traps', 'gnmi': 'gnmi', 'cisco_telemetry_mdt': 'mdt'}

# Most specific first: "connection refused" can sit inside a gRPC "Unavailable".
KINDS = (
    ('auth', re.compile(r'unknown user ?name|wrong digest|authentication fail|authenticationfailure|'
                        r'decryption error|unknown security name|not in time window|code = unauthenticated|'
                        r'code = permissiondenied|401 unauthorized|403 forbidden|login refused|'
                        r'refused the (login|api key)|invalid credentials|incorrect password', re.I)),
    ('tls', re.compile(r'x509|certificate|tls: |handshake fail|sslerror', re.I)),
    ('refused', re.compile(r'connection refused|econnrefused', re.I)),
    ('unreachable', re.compile(r'no route to host|network is unreachable|host is down|'
                               r'no such host|name resolution|server misbehaving|name or service not known|'
                               r'failed to resolve|temporary failure in name', re.I)),
    ('timeout', re.compile(r'timeout|timed out|deadline exceeded|no response', re.I)),
    ('listen', re.compile(r'address already in use|bind: permission denied|listen (udp|tcp)', re.I)),
)

LINE_RE = re.compile(r'\b([EW])! \[inputs\.([a-z0-9_]+)(?:::([^\]]+))?\] (?:Error in plugin: )?(.*)$')
ADDRESS_RE = re.compile(r'agent (?:udp|tcp)://(\S+?):\s|dial tcp ([^\s"]+?):\s|(\d{1,3}(?:\.\d{1,3}){3}:\d+)')
MAX_DETAIL = 300
# A per-VLAN MAC table poll (telegraf.VLAN_ALIAS): "<device>@vlan<id>".
VLAN_ALIAS_RE = re.compile(r'^(.+)@vlan(\d{1,4})$')
TABLE_RE = re.compile(r'gathering table (\w+)')


def kind_of(text):
    """What went wrong, from an error's text: auth, tls, refused, unreachable, timeout, listen or
    other."""
    for kind, pattern in KINDS:
        if pattern.search(text or ''):
            return kind
    return 'other'


def address_of(text):
    found = ADDRESS_RE.search(text or '')
    return next((g for g in found.groups() if g), '') if found else ''


def parse_line(line):
    """A Telegraf log line about an input: {device, driver, kind, address, detail}, or None for
    the rest (start-up, info, warnings that aren't about a device)."""
    found = LINE_RE.search(line or '')
    if not found:
        return None
    level, plugin, alias, text = found.groups()
    if level != 'E':
        return None
    driver = DRIVER_OF.get(plugin, plugin)
    # The listeners (traps, MDT) serve every device: their alias is the driver, not a device.
    device = alias if alias and alias != driver else ''
    vlan = VLAN_ALIAS_RE.match(device)
    table = TABLE_RE.search(text)
    found = {'device': vlan.group(1) if vlan else device, 'driver': driver, 'kind': kind_of(text),
             'address': address_of(text), 'detail': text.strip()[:MAX_DETAIL]}
    if vlan:
        found['vlan'] = int(vlan.group(2))
    if table:
        found['table'] = table.group(1)
    return found


class Problems:
    """The current problem per (device, driver), forgotten once it stops repeating or the device
    sends again. Thread-safe: Telegraf's output is read on its own thread."""

    def __init__(self, forget_after=FORGET_AFTER):
        self._lock = threading.Lock()
        self._found = {}
        self.forget_after = forget_after

    def note(self, problem, now=None):
        """Remember one. True when it is new or changed kind (worth a line in the agent's log)."""
        now = time.time() if now is None else now
        # One table's or VLAN's problem is kept apart from the device's own, so a device that goes
        # silent altogether is still said (and logged), not hidden behind "no answer for VLAN 1".
        key = (problem.get('device') or '', problem['driver'], scope(problem))
        with self._lock:
            old = self._found.get(key)
            first = old['since'] if old and old['kind'] == problem['kind'] else now
            self._found[key] = {**problem, 'device': key[0], 'since': first, 'at': now,
                                'count': (old['count'] + 1) if old and old['kind'] == problem['kind'] else 1}
            return not old or old['kind'] != problem['kind']

    def clear(self, device, driver=None):
        with self._lock:
            for key in [k for k in self._found if k[0] == device and (driver is None or k[1] == driver)]:
                del self._found[key]

    def heard(self, devices, at):
        """Devices that sent points at ``at``: a problem older than that is over. Not one table's
        or one VLAN's: the device's other polls answer while that one keeps failing, so it ends
        only by not coming back (``forget_after``), not flapping (and logging) every minute."""
        with self._lock:
            for key in [k for k, p in self._found.items()
                        if k[0] in devices and p['at'] < at - 1 and not _partial(p)]:
                del self._found[key]

    def sync(self, driver_errors, now=None):
        """Replace the API pollers' problems with this round's ({device: (driver, message, address)})."""
        now = time.time() if now is None else now
        with self._lock:
            for key in [k for k, p in self._found.items() if p.get('poller') and k[0] not in driver_errors]:
                del self._found[key]
        for device, (driver, message, *address) in driver_errors.items():
            where = (address[0] if address else '') or address_of(message)
            self.note({'device': device, 'driver': driver, 'kind': kind_of(message), 'address': where,
                       'detail': str(message)[:MAX_DETAIL], 'poller': True}, now)

    def current(self, now=None):
        """Every problem still going, worst kinds first, then by device."""
        now = time.time() if now is None else now
        with self._lock:
            for key in [k for k, p in self._found.items() if now - p['at'] > self.forget_after and not p.get('poller')]:
                del self._found[key]
            found = [dict(p) for p in self._found.values()]
        order = {kind: n for n, (kind, _) in enumerate(KINDS)}
        return sorted(found, key=lambda p: (order.get(p['kind'], len(order)), p['device'], p['driver']))

    def of(self, device, now=None):
        return [p for p in self.current(now) if p['device'] == device]


def _partial(problem):
    return bool(problem.get('vlan') or problem.get('table'))


def partial(problem):
    """Is it one VLAN's or one table's problem, while the device may well send the rest?"""
    return _partial(problem)


def scope(problem):
    if problem.get('vlan'):
        return 'vlan'
    return problem.get('table') or ''


def hint(problem, port=None):
    """One plain sentence on what to look at. English: the hosted side translates by ``kind``."""
    where = problem.get('address') or 'the device'
    driver = problem.get('driver')
    if problem['kind'] == 'refused':
        what = driver.upper() if driver else 'it'
        return f'nothing listens for {what} on {where}: is it turned on there, and the port right?'
    if problem['kind'] == 'timeout' and driver == 'snmp' and problem.get('vlan'):
        vlan = problem['vlan']
        return (f'no answer from {where} for VLAN {vlan} (community@{vlan}, or context vlan-{vlan} with SNMPv3): '
                f'if its other data comes in, the switch doesn\'t have that VLAN (fix telemetry_vlans), or the '
                f'SNMPv3 user may not read vlan- contexts')
    if problem['kind'] == 'timeout' and driver == 'snmp' and problem.get('table'):
        return (f'no answer from {where} while reading {problem["table"]}: if its other data comes in, the walk '
                f'is too slow (a big table, or SNMP rate limited on the device); if nothing comes in, check '
                f'the community or SNMPv3 login, and that an ACL lets the agent in')
    if problem['kind'] == 'timeout':
        if driver == 'snmp':
            return f'no answer from {where}: check the community or SNMPv3 login, and that an ACL lets the agent in'
        return f'no answer from {where}: is it reachable from the agent, and the port right?'
    if problem['kind'] == 'auth':
        return f'{where} refused the login: check the user and password (or SNMPv3 keys)'
    if problem['kind'] == 'unreachable':
        return f'the agent has no route to {where}: check the address and the agent\'s network'
    if problem['kind'] == 'tls':
        return f'TLS with {where} failed: check its certificate, or turn off "Check TLS" for it'
    if problem['kind'] == 'listen':
        return 'Telegraf cannot open its listening port: is another program (an old telegraf container?) using it?'
    return problem.get('detail') or 'see the agent\'s log'
