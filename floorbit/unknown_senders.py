"""Devices that send to the agents but aren't in the inventory (issue #1443). Docs: docs/inventory.md.

A switch the crew forgot to add, or one with a new management address, looks silent although it
talks. Each address that sent in the last 24 hours without matching a device is listed here with
what it sent (syslog, traps, streams, flows), how often, first and last heard, through which agent,
and the name it gives. Only these counts, never the lines.

- **Syslog** is seen here: the agents relay every line and Floorbit checks the allow-list
  (floorbit/syslog.py). A sender outside the allow-list is still dropped, but noted.
- **Traps and streams** (gNMI, MDT) reach Telegraf on the agent; the telemetry part notes points
  from an address it can't place (floorbit/telemetry/state.py) and answers them with its devices.
- **Flows**: the exporters in the agent's traffic summary (floorbit/flows/store.py).

Ignored addresses are kept under ``unknown_senders_ignored`` in data.json, so the list stays short.
"""
import ipaddress
import threading
import time

WINDOW = 24 * 3600
MOST = 200            # addresses kept per list; the quietest go first
KINDS = ('syslog', 'trap', 'stream', 'flow')
IGNORED = 'unknown_senders_ignored'


class Seen:
    """Addresses heard from, by kind. Thread-safe: the receivers note while pages read."""

    def __init__(self, most=MOST):
        self._lock = threading.Lock()
        self._most = most
        self._rows = {}

    def note(self, kind, address, name='', agent='', count=1, now=None):
        now = time.time() if now is None else now
        key = (kind, str(address))
        with self._lock:
            row = self._rows.get(key)
            if row is None:
                if len(self._rows) >= self._most:
                    self._forget(now)
                    if len(self._rows) >= self._most:
                        del self._rows[min(self._rows, key=lambda k: self._rows[k]['last'])]
                row = self._rows[key] = {'kind': kind, 'address': str(address), 'name': '', 'count': 0,
                                         'first': now, 'last': now, 'agents': set()}
            row['count'] += count
            row['first'], row['last'] = min(row['first'], now), max(row['last'], now)
            if name:
                row['name'] = str(name)[:120]
            if agent:
                row['agents'].add(str(agent)[:80])

    def _forget(self, now):
        for key in [k for k, r in self._rows.items() if r['last'] < now - WINDOW]:
            del self._rows[key]

    def rows(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._forget(now)
            return [{**r, 'agents': sorted(r['agents'])} for r in self._rows.values()]

    def clear(self):
        with self._lock:
            self._rows.clear()


# Syslog's, noted in floorbit/syslog.py where the lines come in.
syslog = Seen()


def _flows(now):
    """Exporters in the agent's traffic summary."""
    from .flows import store
    snap = store.latest() or {}
    out = []
    for e in snap.get('exporters') or []:
        if isinstance(e, dict) and isinstance(e.get('address'), str):
            last = e.get('last') if isinstance(e.get('last'), (int, float)) else now
            out.append({'kind': 'flow', 'address': e['address'], 'name': '', 'count': int(e.get('flows') or 0),
                        'first': last, 'last': last, 'agents': [str(snap['agent'])] if snap.get('agent') else []})
    return out


def _telemetry():
    """What each agent's telemetry part heard from addresses it can't place (``senders``)."""
    from . import agent_plugins, sources
    from .plugins.base import PluginError
    spec = sources.registry.specs.get('telemetry') if sources.registry is not None else None
    if spec is None:
        return []
    try:
        answers = agent_plugins.ask(spec, 'call', 'devices', {})
    except PluginError:
        return []
    out = []
    for a in answers:
        result = a.get('result') if isinstance(a.get('result'), dict) else {}
        for s in result.get('senders') or []:
            if not isinstance(s, dict) or s.get('kind') not in KINDS or not isinstance(s.get('address'), str):
                continue
            nums = {k: s.get(k) for k in ('count', 'first', 'last')}
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in nums.values()):
                continue
            out.append({'kind': s['kind'], 'address': s['address'][:80], 'name': str(s.get('name') or '')[:120],
                        **nums, 'agents': [str(a.get('name') or a.get('agent') or '')][:1]})
    return out


def _known(data):
    """Every management address and name of an inventory device, hidden ones too: a hidden device
    is one the crew decided about."""
    from . import inventory
    out = set()
    for dev in inventory.devices(data, include_hidden=True):
        if dev.get('mgmt_ip'):
            out.add(str(dev['mgmt_ip']).split('/')[0].lower())
        out.add(str(dev.get('name') or '').lower())
    out.discard('')
    return out


def _clean(address):
    try:
        return str(ipaddress.ip_address(str(address).split('%')[0]))
    except ValueError:
        return str(address)[:80]


def ignored(data):
    value = data.get(IGNORED)
    return [str(a) for a in value] if isinstance(value, list) else []


def set_ignored(data, address, on=True):
    """Ignore an address, or take it back. Returns the list."""
    address = _clean(address)
    now = [a for a in ignored(data) if a != address]
    if on:
        now.append(address)
    data[IGNORED] = now[-1000:]
    return data[IGNORED]


def collect(data, now=None, ask_agents=True):
    """One row per address that sent but matches no device: ``{address, name, kinds: {kind: count},
    first, last, agents, ignored}``, the latest first."""
    now = time.time() if now is None else now
    rows = syslog.rows(now)
    for part in (_flows, _telemetry) if ask_agents else (_flows,):
        try:
            rows += part(now) if part is _flows else part()
        except Exception as exc:  # noqa: BLE001  # one source that fails leaves the others
            print(f'[unknown senders] {exc}')
    known, skip = _known(data), set(ignored(data))
    by = {}
    for r in rows:
        address = _clean(r['address'])
        if address.lower() in known or (r.get('name') or '').lower() in known or r['last'] < now - WINDOW:
            continue
        out = by.setdefault(address, {'address': address, 'name': '', 'kinds': {}, 'first': r['first'],
                                      'last': r['last'], 'agents': set(), 'ignored': address in skip})
        out['kinds'][r['kind']] = out['kinds'].get(r['kind'], 0) + r['count']
        out['first'], out['last'] = min(out['first'], r['first']), max(out['last'], r['last'])
        out['name'] = out['name'] or r.get('name') or ''
        out['agents'].update(a for a in r.get('agents') or [] if a)
    found = [{**r, 'agents': sorted(r['agents'])} for r in by.values()]
    return sorted(found, key=lambda r: -r['last'])[:MOST]


def problems(data):
    """One row under the problems' "look at" list while some sender isn't in the inventory or ignored."""
    try:
        found = [r for r in collect(data, ask_agents=False) if not r['ignored']]
    except Exception:  # noqa: BLE001  # the problems page must show without this
        return []
    if not found:
        return []
    return [{'id': 'unknown-senders', 'kind': 'unknown-senders', 'level': 'warn',
             'title': "1 address sends but isn't in the inventory" if len(found) == 1
             else f"{len(found)} addresses send but aren't in the inventory",
             'where': ', '.join(r['name'] or r['address'] for r in found[:3]) + (' …' if len(found) > 3 else ''),
             'since': min(r['first'] for r in found), 'switch_id': None, 'link': '/inventory?view=unknown'}]
