"""Servers and services (issue #471): the ISP uplinks, the DNS resolvers and the LAN cache.

- **ISP uplinks**: a port on a router or firewall with the line's capacity, and optionally a host
  to probe. Floorbit reads the port from the monitoring source (state, traffic in and out against
  the capacity) and connects to the probe host a few times for latency and loss
  (floorbit/probes.py).
- **DNS resolvers**: an address and a name to look up. Floorbit asks each one and keeps how long
  it took and what came back.
- **The LAN cache**: what floorbit/lancache.py read from its log this hour, and how full its disk
  is when ``LANCACHE_CACHE_DIR`` points at it.

Uplinks and resolvers are kept in data.json under ``services`` and changed with ``floorplan.edit``.
A background thread checks them every ``SERVICES_INTERVAL`` seconds (default 30); with a local
agent enrolled the agent sends the probes, from the event network. Uplinks and resolvers also show
on the service health wall.
"""
import ipaddress
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import current_app, has_app_context

from integrations import config

from . import inventory, lancache, links, probes
from .store import load_data, save_data

KEY = 'services'
KINDS = ('uplinks', 'resolvers')
MAX = 30                       # of each kind
HISTORY = 60                   # latency samples kept (30 minutes at the default interval)
HOST_RE = re.compile(r'^[A-Za-z0-9]([A-Za-z0-9.-]{0,252}|[0-9a-fA-F:.]{0,44})$')
WARN_UTIL = 0.8                # an uplink this full is amber
WARN_LOSS = 0.2
WARN_UPLINK_MS = 100
WARN_DNS_MS = 200
WARN_DISK = 0.9
RANK = {'router': 0, 'firewall': 1, 'switch': 2}   # where a line comes in, most likely first
_lock = threading.Lock()


class ServiceError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _stored(data):
    raw = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    return {k: [r for r in raw.get(k) or [] if isinstance(r, dict) and r.get('id')] for k in KINDS}


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _host(value, message, required=True):
    host = str(value or '').strip()
    if not host and not required:
        return ''
    if not HOST_RE.match(host):
        raise ServiceError(message)
    return host


def _clean_uplink(body, data, old):
    name = _text(body.get('name', old.get('name')), 60)
    if not name:
        raise ServiceError('Name the uplink, like the provider.')
    devices = {str(d['name']).lower(): d['name'] for d in inventory.devices(data, include_hidden=True) if d.get('name')}
    device = devices.get(str(body.get('device', old.get('device')) or '').strip().lower())
    if not device:
        raise ServiceError('Pick the router or firewall the line is on from the inventory.')
    port = str(body.get('port', old.get('port')) or '').strip()
    if not links.PORT_RE.match(port):
        raise ServiceError('Name the port, like Te1/0/48.')
    try:
        capacity = int(body.get('capacity_mbps', old.get('capacity_mbps')) or 0)
    except (TypeError, ValueError):
        capacity = 0
    if not 1 <= capacity <= 400_000:
        raise ServiceError("The line's capacity is a number of Mbit/s.")
    probe = _host(body.get('probe_host', old.get('probe_host')), 'The probe host is a name or an IP address.',
                  required=False)
    try:
        probe_port = int(body.get('probe_port', old.get('probe_port')) or 443)
    except (TypeError, ValueError):
        probe_port = 0
    if probe_port not in probes.PROBE_PORTS:
        raise ServiceError(f"The probe port is one of {', '.join(map(str, probes.PROBE_PORTS))}.")
    return {'name': name, 'device': device, 'port': port, 'capacity_mbps': capacity, 'probe_host': probe,
            'probe_port': probe_port}


def _clean_resolver(body, _data, old):
    name = _text(body.get('name', old.get('name')), 60)
    if not name:
        raise ServiceError('Name the resolver.')
    try:
        address = str(ipaddress.ip_address(str(body.get('address', old.get('address')) or '').strip()))
    except ValueError:
        raise ServiceError("The resolver's address is an IP address.") from None
    lookup = str(body.get('lookup', old.get('lookup')) or '').strip().strip('.').lower()
    try:
        probes._name(lookup)
    except (probes.ProbeError, UnicodeError):
        raise ServiceError('The name to look up is a domain name, like example.com.') from None
    if '.' not in lookup:
        raise ServiceError('The name to look up is a domain name, like example.com.')
    return {'name': name, 'address': address, 'lookup': lookup}


CLEAN = {'uplinks': _clean_uplink, 'resolvers': _clean_resolver}


def save(kind, body, by, item_id=None):
    with _lock:
        data = load_data()
        stored = _stored(data)
        rows = stored[kind]
        row = next((r for r in rows if r['id'] == item_id), None) if item_id else None
        if item_id and row is None:
            raise ServiceError('Not found.', 404)
        fields = CLEAN[kind](body, data, row or {})
        if row is None:
            if len(rows) >= MAX:
                raise ServiceError(f'Floorbit keeps at most {MAX} of each.')
            row = {'id': uuid.uuid4().hex[:12]}
            rows.append(row)
        row.update(fields, updated_at=time.time(), by=by)
        data[KEY] = stored
        save_data(data)
    poller.forget(row['id'])
    return dict(row)


def delete(kind, item_id):
    with _lock:
        data = load_data()
        stored = _stored(data)
        gone = next((r for r in stored[kind] if r['id'] == item_id), None)
        if gone is None:
            return None
        stored[kind] = [r for r in stored[kind] if r is not gone]
        data[KEY] = stored
        save_data(data)
    poller.forget(item_id)
    return gone


# ── checking ────────────────────────────────────────────────────────────────
def _via_agent():
    from . import agent_link
    return agent_link.active()


def _ask(method, *args):
    """Run a probe here, or on the local agent when one is enrolled (it is on the event network)."""
    demo = probes.stood_in(method, args)
    if demo is not None:
        return demo
    if not _via_agent():
        return {'dns_probe': probes.dns, 'tcp_probe': probes.tcp}[method](probes.target(args[0]), *args[1:])
    from . import agent_link
    try:
        return agent_link.tunnel.call(method, args, timeout=20)
    except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
        raise probes.ProbeError(str(exc)) from None


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def check_uplink(uplink, now):
    read = links.reader.ports(uplink['device'], now)
    port = (read or {}).get(links._canon(uplink['port'])) if read is not None else None
    cap = uplink['capacity_mbps'] * 1e6
    out = {'port_state': None, 'in_bps': None, 'out_bps': None, 'utilization': None, 'latency_ms': None,
           'loss': None, 'error': ''}
    if port is not None:
        state = port.get('state')
        out['port_state'] = state if state in ('up', 'down', 'errors', 'disabled') else 'unknown'
        # The router's side: in is what comes from the internet, out what goes to it.
        out['in_bps'], out['out_bps'] = _num(port.get('upload_bps')), _num(port.get('download_bps'))
        busiest = max(out['in_bps'] or 0, out['out_bps'] or 0)
        out['utilization'] = round(min(busiest / cap, 9.99), 4) if out['port_state'] in ('up', 'errors') else None
    elif read is None:
        out['error'] = f"{uplink['device']} can't be read."
    else:
        out['error'] = f"{uplink['device']} has no port {uplink['port']}."
    if uplink.get('probe_host'):
        try:
            got = _ask('tcp_probe', uplink['probe_host'], uplink['probe_port'], 5)
            sent = max(1, int(got.get('sent') or 1))
            out['loss'] = round(min(int(got.get('lost') or 0), sent) / sent, 2)
            out['latency_ms'] = _num(got.get('avg_ms'))
        except (probes.ProbeError, ValueError, TypeError) as exc:
            out['error'] = out['error'] or str(exc)
    if out['port_state'] in ('down', 'disabled') or out['loss'] == 1:
        status = 'down'
    elif out['port_state'] is None and out['loss'] is None:
        status = 'unknown'
    elif (out['utilization'] or 0) >= WARN_UTIL or (out['loss'] or 0) >= WARN_LOSS \
            or (out['latency_ms'] or 0) >= WARN_UPLINK_MS or out['port_state'] == 'errors':
        status = 'warn'
    else:
        status = 'up'
    return status, out


def check_resolver(resolver, _now):
    try:
        got = _ask('dns_probe', resolver['address'], resolver['lookup'])
    except probes.ProbeError as exc:
        return 'down', {'latency_ms': None, 'rcode': None, 'answers': None, 'error': str(exc)}
    out = {'latency_ms': _num(got.get('ms')), 'rcode': str(got.get('rcode') or '')[:10],
           'answers': _num(got.get('answers')), 'error': ''}
    if out['rcode'] != 'NOERROR' or not out['answers']:
        return 'down', {**out, 'error': f"{resolver['lookup']}: {out['rcode'] or 'no answer'}"}
    return ('warn' if (out['latency_ms'] or 0) >= WARN_DNS_MS else 'up'), out


CHECK = {'uplinks': check_uplink, 'resolvers': check_resolver}


class Poller:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {}          # id -> {status, since, checked_at, history, **values}
        self._thread = None
        self._stop = threading.Event()
        self.last_poll = None

    @staticmethod
    def interval():
        return config.get_int('SERVICES_INTERVAL', 30, minimum=10)

    def forget(self, item_id):
        with self._lock:
            self._state.pop(item_id, None)

    def reset(self):
        with self._lock:
            self._state, self.last_poll = {}, None

    def check(self, kind, item, now=None):
        now = time.time() if now is None else now
        try:
            status, values = CHECK[kind](item, now)
        except Exception as exc:  # noqa: BLE001 - one broken check must not stop the others
            status, values = 'unknown', {'error': str(exc)[:200]}
        with self._lock:
            old = self._state.get(item['id']) or {}
            history = [*(old.get('history') or [])[-(HISTORY - 1):], [round(now), values.get('latency_ms')]]
            self._state[item['id']] = {**values, 'status': status, 'checked_at': now, 'history': history,
                                       'since': old['since'] if old.get('status') == status else now}
        return self.state(item['id'])

    def poll_once(self, now=None):
        stored = _stored(load_data())
        jobs = [(kind, item) for kind in KINDS for item in stored[kind]]
        if jobs:
            with ThreadPoolExecutor(min(8, len(jobs))) as pool:
                list(pool.map(lambda j: self.check(*j, now), jobs))
        with self._lock:
            known = {item['id'] for _k, item in jobs}
            for gone in set(self._state) - known:
                self._state.pop(gone)
            self.last_poll = time.time() if now is None else now

    def state(self, item_id):
        with self._lock:
            found = self._state.get(item_id)
            return dict(found) if found else {'status': 'unknown', 'checked_at': None, 'since': None, 'history': [],
                                              'error': ''}

    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='services', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                stored = _stored(load_data())
                if any(stored.values()):
                    self.poll_once()
            except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                print(f'[services] poll failed: {exc}')
            self._stop.wait(self.interval())


poller = Poller()


def lan_cache(now=None):
    """The LAN cache this hour (hit ratio, bytes served) and how full its disk is, or None when
    Floorbit reads no cache log."""
    # The health wall asks from its own thread, outside a request.
    stats = current_app.extensions.get('floorbit_lancache') if has_app_context() else lancache._stats
    snap = stats.snapshot(hours=1, now=now) if stats is not None else None
    path = config.get('LANCACHE_CACHE_DIR', '') or ''
    disk = None
    if path:
        try:
            usage = shutil.disk_usage(path)
            disk = {'used': usage.used, 'total': usage.total, 'ratio': round(usage.used / usage.total, 4)}
        except OSError:
            disk = None
    if not (snap and snap.get('configured')) and disk is None:
        return None
    served = (snap or {}).get('hit_bytes', 0) + (snap or {}).get('miss_bytes', 0)
    hour = (now or time.time()) % 3600 or 1
    status = 'warn' if disk and disk['ratio'] >= WARN_DISK else 'up'
    if snap and snap.get('error'):
        status = 'warn'
    return {'status': status, 'hit_ratio': (snap or {}).get('hit_ratio'), 'served_bytes': served,
            'bps': round(served * 8 / hour) if served else 0, 'disk': disk,
            'error': (snap or {}).get('error') or '', 'demo': bool((snap or {}).get('demo'))}


def overview(now=None):
    data = load_data()
    stored = _stored(data)
    new = [(kind, item) for kind in KINDS for item in stored[kind] if poller.state(item['id'])['checked_at'] is None]
    if new:
        # Just added, or no background thread (tests, a one-off): check now rather than show them grey.
        with ThreadPoolExecutor(min(8, len(new))) as pool:
            list(pool.map(lambda j: poller.check(*j, now), new))
    out = {kind: [{**item, **poller.state(item['id'])} for item in stored[kind]] for kind in KINDS}
    out.update(lan_cache=lan_cache(now), interval=poller.interval(), last_poll=poller.last_poll,
               via_agent=_via_agent(), probe_ports=list(probes.PROBE_PORTS),
               # Where a line can come in, for the form: routers and firewalls first.
               devices=[d['name'] for d in sorted((d for d in inventory.devices(data) if d.get('name')),
                                                  key=lambda d: (RANK.get(d.get('role'), 3), str(d['name']).lower()))])
    return out


def _mbit(bps):
    return f'{bps / 1e6:.0f}' if bps is not None else '?'


def health_checks():
    """Uplinks and resolvers as tiles of the service health wall (floorbit/health.py)."""
    stored = _stored(load_data())
    out = []
    for up in stored['uplinks']:
        s = poller.state(up['id'])
        if s['status'] == 'unknown':
            summary = s.get('error') or 'Not checked yet.'
        elif s.get('port_state') in ('down', 'disabled'):
            summary = f"{up['device']} {up['port']} is down."
        else:
            summary = f"{_mbit(s.get('in_bps'))} / {up['capacity_mbps']} Mbit/s in"
        metrics = [m for m in (
            {'label': 'Used', 'value': round(s['utilization'] * 100), 'unit': '%',
             'tone': 'warn' if s['utilization'] >= WARN_UTIL else ''} if s.get('utilization') is not None else None,
            {'label': 'Latency', 'value': s.get('latency_ms'), 'unit': 'ms', 'tone': ''}
            if s.get('latency_ms') is not None else None,
            {'label': 'Loss', 'value': round(s['loss'] * 100), 'unit': '%', 'tone': 'warn' if s['loss'] else ''}
            if s.get('loss') is not None else None) if m]
        out.append({'id': f"uplink:{up['id']}", 'name': up['name'], 'kind': 'uplink', 'status': s['status'],
                    'summary': summary, 'metrics': metrics, 'link': '/services',
                    'plugin': 'services', 'plugin_name': 'Services'})
    for res in stored['resolvers']:
        s = poller.state(res['id'])
        summary = (s.get('error') or 'Not checked yet.') if s['status'] in ('down', 'unknown') \
            else f"{res['lookup']} in {s.get('latency_ms')} ms"
        metrics = [{'label': 'Answer', 'value': s.get('latency_ms'), 'unit': 'ms', 'tone': ''}] \
            if s.get('latency_ms') is not None else []
        out.append({'id': f"dns:{res['id']}", 'name': res['name'], 'kind': 'dns', 'status': s['status'],
                    'summary': summary, 'metrics': metrics, 'link': '/services',
                    'plugin': 'services', 'plugin_name': 'Services'})
    cache = lan_cache()
    if cache is not None and not cache['demo']:
        out.append(_cache_tile(cache))
    return out


def _cache_tile(cache):
    disk, hit = cache['disk'], cache['hit_ratio']
    if cache['error']:
        summary = cache['error']
    elif disk and disk['ratio'] >= WARN_DISK:
        summary = f"The cache disk is {round(disk['ratio'] * 100)} % full."
    elif hit is not None:
        summary = f"{round(hit * 100)} % served from the cache this hour"
    else:
        summary = 'Nothing downloaded this hour.'
    metrics = [m for m in (
        {'label': 'Hits', 'value': round(hit * 100), 'unit': '%', 'tone': ''} if hit is not None else None,
        {'label': 'Disk', 'value': round(disk['ratio'] * 100), 'unit': '%',
         'tone': 'warn' if disk['ratio'] >= WARN_DISK else ''} if disk else None) if m]
    return {'id': 'lancache', 'name': 'LAN cache', 'kind': 'cache', 'status': cache['status'],
            'summary': summary, 'metrics': metrics, 'link': '/services',
            'plugin': 'services', 'plugin_name': 'Services'}


def init_app(app, start_background=True):
    app.extensions['floorbit_services'] = poller
    started = threading.Event()

    @app.before_request
    def start_services_once():
        if start_background and not started.is_set():
            started.set()
            poller.start()
