"""Drivers that are API calls rather than Telegraf inputs: NX-API on a Nexus, RESTCONF on IOS-XE,
and the OPNsense API. Each poll returns lineproto.Points in the shapes state.py reads, so they go
the same way as Telegraf's (latest picture, then storage).

They run where the collector runs: in Floorbit when it is self-hosted, on the local agent when it
is hosted (the agent gets the targets with their secrets over its TLS link). Logins are opened
for one poll and dropped.
"""
import time

import requests

from .lineproto import Point
from .telegraf import port

TIMEOUT = 8


class PollError(RuntimeError):
    pass


class LoginRefused(PollError):
    """The device said no to the login: not tried again until someone fixes it, so a wrong password
    never locks the account out or fills the AAA server with alarms."""


def _session(t, user=None, password=None):
    s = requests.Session()
    # Devices sit on the event network: never send their logins through a proxy from the environment.
    s.trust_env = False
    s.verify = bool(t.get('verify_tls', True))
    if user is not None:
        s.auth = (user, password or '')
    return s


def _base(t, default_scheme='https'):
    if t.get('url'):
        return t['url'].rstrip('/')
    host = t['address']
    host = f'[{host}]' if ':' in host else host
    at = port(t, 'api')
    return f'{default_scheme}://{host}' + (f':{at}' if at else '')


def _tags(t, driver, **extra):
    return {'device': t['name'], 'address': t['address'], 'driver': driver, 'kind': t.get('kind') or 'switch',
            **{k: str(v) for k, v in extra.items() if v not in (None, '')}}


def _rows(body, *path):
    """NX-API nests tables as TABLE_x/ROW_x, and a single row comes as an object, not a list."""
    for key in path:
        if isinstance(body, list):
            body = body[0] if body else {}
        body = (body or {}).get(key) if isinstance(body, dict) else None
    if body is None:
        return []
    return body if isinstance(body, list) else [body]


# ── NX-API ─────────────────────────────────────────────────────────────────────────────────────

def nxapi(t, now=None):
    """``show ip arp vrf all`` and ``show interface`` over NX-API JSON-RPC."""
    now = time.time() if now is None else now
    s = _session(t, t.get('username') or '', t.get('password'))
    calls = [{'jsonrpc': '2.0', 'method': 'cli', 'params': {'cmd': cmd, 'version': 1}, 'id': i}
             for i, cmd in enumerate(('show ip arp vrf all', 'show interface'), 1)]
    try:
        resp = s.post(_base(t) + '/ins', json=calls, headers={'content-type': 'application/json-rpc'},
                      timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise PollError(f'NX-API on {t["name"]}: {type(exc).__name__}') from None
    if resp.status_code == 401:
        raise LoginRefused(f'NX-API on {t["name"]} refused the login.')
    if not resp.ok:
        raise PollError(f'NX-API on {t["name"]} answered {resp.status_code}.')
    try:
        answers = resp.json()
    except ValueError:
        raise PollError(f'NX-API on {t["name"]} did not answer JSON.') from None
    answers = answers if isinstance(answers, list) else [answers]
    by_id = {a.get('id'): (a.get('result') or {}).get('body') or {} for a in answers if isinstance(a, dict)}
    points = []
    for row in _rows(by_id.get(1), 'TABLE_vrf', 'ROW_vrf', 'TABLE_adj', 'ROW_adj'):
        ip, mac = row.get('ip-addr-out'), row.get('mac')
        if ip and mac and mac.upper() != 'INCOMPLETE':
            points.append(Point('fb_arp', _tags(t, 'nxapi', ip=ip, port=row.get('intf-out')), {'mac': mac}, now))
    for row in _rows(by_id.get(2), 'TABLE_interface', 'ROW_interface'):
        name = row.get('interface')
        if not name:
            continue
        fields = {'oper_status': row.get('state') or row.get('svi_line_proto'),
                  'admin_status': row.get('admin_state') or row.get('svi_admin_state'),
                  'eth_inbytes': row.get('eth_inbytes'), 'eth_outbytes': row.get('eth_outbytes'),
                  'eth_inerr': row.get('eth_inerr'), 'eth_outerr': row.get('eth_outerr'),
                  'eth_speed': _mbit(row.get('eth_speed')), 'ifAlias': row.get('desc')}
        fields = {k: _number(v) if k.startswith('eth_') else v for k, v in fields.items() if v not in (None, '')}
        if fields:
            points.append(Point('fb_if', _tags(t, 'nxapi', ifName=name), fields, now))
    return points


def _number(value):
    try:
        return float(str(value).strip())
    except ValueError:
        return value


def _mbit(text):
    """NX-OS says ``10 Gb/s`` or ``1000 Mb/s``; as Mbit/s."""
    parts = str(text or '').split()
    if not parts:
        return None
    try:
        number = float(parts[0])
    except ValueError:
        return None
    unit = parts[1].lower() if len(parts) > 1 else 'mb/s'
    return number * 1000 if unit.startswith('gb') else number


# ── RESTCONF (IOS-XE 16+) ──────────────────────────────────────────────────────────────────────

def restconf(t, now=None):
    """ARP (Cisco-IOS-XE-arp-oper) and interfaces (Cisco-IOS-XE-interfaces-oper): the same models
    MDT streams, read on request."""
    now = time.time() if now is None else now
    s = _session(t, t.get('username') or '', t.get('password'))
    headers = {'Accept': 'application/yang-data+json'}
    points = []

    def get(path):
        try:
            resp = s.get(_base(t) + '/restconf/data/' + path, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise PollError(f'RESTCONF on {t["name"]}: {type(exc).__name__}') from None
        if resp.status_code == 401:
            raise LoginRefused(f'RESTCONF on {t["name"]} refused the login.')
        if resp.status_code == 404:
            return {}
        if not resp.ok:
            raise PollError(f'RESTCONF on {t["name"]} answered {resp.status_code}.')
        try:
            return resp.json()
        except ValueError:
            raise PollError(f'RESTCONF on {t["name"]} did not answer JSON.') from None

    arp = get('Cisco-IOS-XE-arp-oper:arp-data')
    for vrf in (arp.get('Cisco-IOS-XE-arp-oper:arp-data') or {}).get('arp-vrf') or []:
        for row in vrf.get('arp-oper') or []:
            if row.get('address') and row.get('hardware'):
                points.append(Point('fb_arp', _tags(t, 'restconf', ip=row['address'], port=row.get('interface')),
                                    {'mac': row['hardware']}, now))
    ifs = get('Cisco-IOS-XE-interfaces-oper:interfaces')
    for row in (ifs.get('Cisco-IOS-XE-interfaces-oper:interfaces') or {}).get('interface') or []:
        stats = row.get('statistics') or {}
        fields = {'oper_status': str(row.get('oper-status') or '').replace('if-oper-state-', ''),
                  'admin_status': str(row.get('admin-status') or '').replace('if-state-', ''),
                  'in_octets': _number(stats.get('in-octets')), 'out_octets': _number(stats.get('out-octets')),
                  'in_errors': _number(stats.get('in-errors')), 'out_errors': _number(stats.get('out-errors')),
                  'ifAlias': row.get('description')}
        speed = _number(row.get('speed'))
        if isinstance(speed, float):
            fields['port_speed'] = speed
        fields = {k: v for k, v in fields.items() if v not in (None, '')}
        if row.get('name') and fields:
            points.append(Point('fb_if', _tags(t, 'restconf', ifName=row['name']), fields, now))
    return points


# ── OPNsense ───────────────────────────────────────────────────────────────────────────────────

def opnsense(t, now=None):
    """Gateways (up, delay, loss), ARP and interface counters from the OPNsense API (an API key
    with the Diagnostics and Status privileges only)."""
    now = time.time() if now is None else now
    s = _session(t, t.get('username') or '', t.get('api_secret') or t.get('password'))
    points = []

    def get(path):
        try:
            resp = s.get(_base(t) + '/api/' + path, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise PollError(f'OPNsense API on {t["name"]}: {type(exc).__name__}') from None
        if resp.status_code in (401, 403):
            raise LoginRefused(f'OPNsense on {t["name"]} refused the API key.')
        if not resp.ok:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    tags = {'kind': 'firewall'}
    for gw in (get('routes/gateway/status') or {}).get('items') or []:
        delay = _number(str(gw.get('delay') or '').replace('ms', '').strip())
        loss = _number(str(gw.get('loss') or '').replace('%', '').strip())
        fields = {'status': str(gw.get('status_translated') or gw.get('status') or '')}
        if isinstance(delay, float):
            fields['delay_ms'] = delay
        if isinstance(loss, float):
            fields['loss_pct'] = loss
        if gw.get('name'):
            points.append(Point('fb_gateway', {**_tags({**t, **tags}, 'opnsense'), 'gateway': gw['name']},
                                fields, now))
    arp = get('diagnostics/interface/getArp')
    for row in arp if isinstance(arp, list) else (arp or {}).get('rows') or []:
        if isinstance(row, dict) and row.get('ip') and row.get('mac'):
            points.append(Point('fb_arp', _tags({**t, **tags}, 'opnsense', ip=row['ip'],
                                                port=row.get('intf_description') or row.get('intf')),
                                {'mac': row['mac']}, now))
    stats = (get('diagnostics/interface/getInterfaceStatistics') or {}).get('statistics') or {}
    for label, row in stats.items():
        if not isinstance(row, dict):
            continue
        name = row.get('name') or label
        fields = {'bytes_recv': _number(row.get('received-bytes')), 'bytes_sent': _number(row.get('sent-bytes')),
                  'err_in': _number(row.get('received-errors')), 'err_out': _number(row.get('send-errors'))}
        fields = {k: v for k, v in fields.items() if isinstance(v, float)}
        if fields:
            points.append(Point('fb_if', _tags({**t, **tags}, 'opnsense', ifName=name), fields, now))
    return points


POLLERS = {'nxapi': nxapi, 'restconf': restconf, 'opnsense': opnsense}


def register(driver, poller):
    """Add an API driver (docs/telemetry.md, "Extending it"): ``poller(target, now)`` returns
    lineproto.Points and raises PollError with a message for the crew. The driver can then be
    picked for a device in the inventory (telemetry_drivers)."""
    from . import targets
    POLLERS[driver] = poller
    if driver not in targets.DRIVERS:
        targets.DRIVERS = (*targets.DRIVERS, driver)


def login_rev(t):
    """Changes when the device's login does (an edited password), so a stopped login is tried again
    with the new one and never with the old."""
    import hashlib

    from .targets import SECRETS
    raw = '|'.join(str(t.get(k) or '') for k in ('username', 'address', *SECRETS))
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def poll_all(targets, now=None, log=print, blocks=None):
    """Every API driver of every target, once. (points, {target name: error}).

    ``blocks``: something with ``may_login(device, credential, rev)`` and
    ``auth_failed(device, credential, rev, message)`` (the agent's context, or AuthBlocks): a login
    the device refused is not tried again until it is cleared or the login changes."""
    points, errors = [], {}
    for t in targets:
        # A device from the inventory: the block goes on its stored login (device, credential,
        # revision), so the inventory shows it and the hosted SSH path leaves it alone too.
        login = (t.get('logins') or {}).get('api')
        device, rev = (login['device'], login['rev']) if login else (t['name'], login_rev(t))
        for driver in t.get('drivers') or []:
            poller = POLLERS.get(driver)
            if poller is None:
                continue
            credential = login['credential'] if login else driver
            if blocks is not None and not blocks.may_login(device, credential, rev):
                errors[t['name']] = f'{driver}: login refused before, not tried again until cleared'
                continue
            try:
                points += poller(t, now)
            except LoginRefused as exc:
                errors[t['name']] = str(exc)
                if blocks is not None:
                    blocks.auth_failed(device, credential, rev, str(exc))
                log(f'[telemetry] {exc}')
            except PollError as exc:
                errors[t['name']] = str(exc)
                log(f'[telemetry] {exc}')
    return points, errors
