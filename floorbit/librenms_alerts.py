"""LibreNMS alerts pushed through the local agent (issue #951, docs/librenms-alerts.md).

LibreNMS sits on the event network; its API transport posts each alert to the agent
(builtin_plugins/librenms-alerts), which checks the token and passes it on. Here every alert becomes
a problem at once, instead of waiting for the next poll, and wakes the status monitor so a switch
LibreNMS saw go down shows offline right away.

An alert is kept under (agent, LibreNMS host, alert id): LibreNMS keeps the alert id from the first
alert to its recovery. State 0 (recovered) clears it; 1 (alert), 3 (worse) and 4 (better) replace
it; 2 means someone acknowledged it in LibreNMS. A port alert lists its ports in ``faults``: the
list each update brings is the whole current list, so a port missing from it is fixed.

Kept in data.json under ``librenms_alerts``: ``token`` (sealed with floorbit/vault.py) and
``active``. Device and port names only, never people.
"""
import calendar
import hashlib
import json
import secrets
import threading
import time

from . import vault
from .store import load_data, save_data

KEY = 'librenms_alerts'
VAULT_NAME = 'librenms-alerts:token'
PORT = 9530               # the plugin's default port on the agent (plugin.yaml)
PATH = '/librenms'
MAX_ACTIVE = 500          # LibreNMS with a broken rule can fire for every port; keep the newest
MAX_PORTS = 64
STATES = {0: 'ok', 1: 'alert', 2: 'acknowledged', 3: 'worse', 4: 'better'}
_lock = threading.Lock()


class AlertError(ValueError):
    """The alert can't be read: wrong body template in LibreNMS."""


def _section(data):
    return data.get(KEY) or {}


def token(create=True):
    """What LibreNMS puts after ``Bearer``. Made on first use: nobody types one in (zero setup)."""
    sealed = _section(load_data()).get('token')
    if sealed:
        return vault.open_(VAULT_NAME, sealed)
    if not create:
        return None
    with _lock:
        data = load_data()
        section = data.setdefault(KEY, {})
        if not section.get('token'):
            section['token'] = vault.seal(VAULT_NAME, 'fbl_' + secrets.token_urlsafe(24))
            save_data(data)
        return vault.open_(VAULT_NAME, section['token'])


def new_token():
    with _lock:
        data = load_data()
        data.setdefault(KEY, {})['token'] = vault.seal(VAULT_NAME, 'fbl_' + secrets.token_urlsafe(24))
        save_data(data)
    return token()


# ── reading one alert ────────────────────────────────────────────────────────────────────

def _text(value, limit=200):
    return ' '.join(str(value).split())[:limit] if value not in (None, '') else ''


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _when(value, now):
    """LibreNMS's ``timestamp`` ("2026-11-19 18:02:11", the LibreNMS server's local time) or a Unix
    time. Unreadable or in the future: now, so a wrong clock can't keep an old alert on top."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        t = float(value)
    else:
        text = _text(value, 40)
        try:
            t = time.mktime(time.strptime(text[:19], '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            try:
                t = calendar.timegm(time.strptime(text[:19], '%Y-%m-%dT%H:%M:%S'))
            except ValueError:
                return now
    return min(t, now)


def _faults(value):
    """``faults`` as a list of rows: LibreNMS gives an object keyed 1, 2, ...; a template may also
    send a list, or the JSON of either as a string."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if isinstance(value, dict):
        value = [value[k] for k in sorted(value, key=lambda k: (_int(k) is None, _int(k) or 0, str(k)))]
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _ports(faults):
    out = []
    for row in faults:
        name = _text(row.get('ifName') or row.get('ifDescr') or row.get('port') or row.get('label'), 64)
        if name and name not in out:
            out.append(name)
    return out[:MAX_PORTS]


def read(payload, now=None):
    """The fields Floorbit uses from one alert, or AlertError."""
    if not isinstance(payload, dict):
        raise AlertError('The alert is not a JSON object.')
    now = time.time() if now is None else now
    host = _text(payload.get('sysName') or payload.get('hostname') or payload.get('display'), 120)
    if not host:
        raise AlertError('The alert names no device: check the body template (hostname).')
    state = _int(payload.get('state'))
    if state not in STATES:
        raise AlertError('The alert has no state: check the body template (state).')
    alert_id = _int(payload.get('alert_id', payload.get('id')))
    rule_id = _int(payload.get('rule_id'))
    if alert_id is None and rule_id is None:
        raise AlertError('The alert has no id: check the body template (alert_id).')
    faults = _faults(payload.get('faults'))
    severity = _text(payload.get('severity'), 20).lower()
    return {'host': host, 'hostname': _text(payload.get('hostname'), 120), 'state': state,
            'alert_id': alert_id, 'rule_id': rule_id, 'device_id': _int(payload.get('device_id')),
            'title': _text(payload.get('title') or payload.get('name') or payload.get('rule')) or 'LibreNMS alert',
            'rule': _text(payload.get('name') or payload.get('rule'), 120),
            'severity': severity if severity in ('critical', 'warning', 'ok') else 'warning',
            'ports': _ports(faults), 'at': _when(payload.get('timestamp'), now)}


def key_of(agent, alert):
    """One entry per alert: the alert id lasts from the alert to its recovery. Without one, the rule
    on the device stands in."""
    ident = f"a{alert['alert_id']}" if alert['alert_id'] is not None else f"r{alert['rule_id']}"
    raw = f"{agent or ''}|{alert['host'].lower()}|{ident}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── keeping them ─────────────────────────────────────────────────────────────────────────

def take(payload, agent=None, now=None):
    """Store, update or clear one alert. Returns what happened ('opened', 'updated', 'cleared',
    'stale', 'unknown'). Any change wakes the status monitor."""
    now = time.time() if now is None else now
    alert = read(payload, now)
    key = key_of(agent, alert)
    with _lock:
        data = load_data()
        active = data.setdefault(KEY, {}).setdefault('active', {})
        old = active.get(key)
        if old and alert['at'] < old.get('at', 0):
            return 'stale'           # the newer one already arrived (the agent's spool can reorder)
        if alert['state'] == 0:
            if not old:
                return 'unknown'
            active.pop(key)
            what = 'cleared'
        else:
            ports = {p: (old or {}).get('ports', {}).get(p) or alert['at'] for p in alert['ports']}
            active[key] = {**alert, 'key': key, 'agent': agent or '', 'ports': ports,
                           'since': (old or {}).get('since') or alert['at'], 'received': now,
                           'acknowledged': alert['state'] == 2 or (bool(old and old.get('acknowledged'))
                                                                   and alert['state'] == 4)}
            what = 'updated' if old else 'opened'
            if len(active) > MAX_ACTIVE:
                for k in sorted(active, key=lambda k: active[k].get('at', 0))[:len(active) - MAX_ACTIVE]:
                    active.pop(k)
        save_data(data)
    _changed()
    return what


def clear(key):
    """The crew clears an alert whose recovery got lost. Returns the entry, or None."""
    with _lock:
        data = load_data()
        found = (_section(data).get('active') or {}).pop(key, None)
        if found is not None:
            save_data(data)
    if found is not None:
        _changed()
    return found


def active(data=None):
    data = load_data() if data is None else data
    return sorted((_section(data).get('active') or {}).values(), key=lambda a: a.get('since') or 0)


def _changed():
    from integrations import events

    from . import sources
    sources.wake_status_monitor()
    try:
        events.publish('alerts.changed', {})
    except Exception as exc:  # noqa: BLE001  # live updates are a nicety; the alert is stored
        print(f'[librenms-alerts] could not publish the change: {exc}')


def problems(data=None):
    """The Problems page's items (floorbit/problems.py)."""
    from urllib.parse import quote

    from . import inventory
    data = load_data() if data is None else data
    by_name = {d['name'].lower(): d for d in inventory.devices(data)}
    out = []
    for a in active(data):
        device = by_name.get(a['host'].lower()) or by_name.get((a.get('hostname') or '').lower())
        name = device['name'] if device else a['host']
        where = f"{name}: {', '.join(a['ports'])}" if a.get('ports') else name
        title = f"{a['title']} (acknowledged in LibreNMS)" if a.get('acknowledged') else a['title']
        out.append({'id': f"librenms:{a['key']}", 'kind': 'librenms',
                    'level': 'down' if a.get('severity') == 'critical' and not a.get('acknowledged') else 'warn',
                    'title': title, 'where': where, 'since': a.get('since'),
                    'link': f'/plan?switch={quote(name)}' if device else '',
                    'switch_id': device['id'] if device else None, 'clear_id': a['key'],
                    'ports': list(a.get('ports') or [])})
    return out


# ── what LibreNMS needs ──────────────────────────────────────────────────────────────────

# The API transport's body. LibreNMS renders it with Blade; @json writes faults as JSON.
# TODO(#951): checked against the LibreNMS docs only; try it on a real LibreNMS before the event.
BODY = """{
  "alert_id": {{ $alert->id }},
  "rule_id": {{ $alert->rule_id }},
  "device_id": {{ $alert->device_id }},
  "hostname": "{{ $alert->hostname }}",
  "sysName": "{{ $alert->sysName }}",
  "state": {{ $alert->state }},
  "severity": "{{ $alert->severity }}",
  "title": "{{ $alert->title }}",
  "name": "{{ $alert->name }}",
  "timestamp": "{{ $alert->timestamp }}",
  "faults": @json($alert->faults)
}"""


def _host_of(url):
    from urllib.parse import urlsplit
    try:
        return urlsplit(url).hostname or ''
    except ValueError:
        return ''


def setup(data=None):
    """Everything to paste into LibreNMS (Alerts > Alert transports > API): one URL per agent, the
    token and the body. The agent's address in the hall is what browsers reached its front door at;
    until one did, the URL says where the address goes."""
    from . import agent_link, agent_plugins
    data = load_data() if data is None else data
    port, registry = PORT, None
    try:
        registry = agent_plugins._registry()
        spec = registry.specs.get('librenms-alerts') if registry is not None else None
        if spec is not None:
            port = int(registry.settings_of(spec).get('port') or 0)
    except Exception as exc:  # noqa: BLE001  # the default port still helps
        print(f'[librenms-alerts] could not read the port setting: {exc}')
    from . import agent_settings
    agents = []
    for a in agent_link.all_agents(data):
        report = a.get('report') or {}
        host = _host_of(report.get('lan_url') or '')
        mine = int((agent_settings.overrides(a['id'], data).get('librenms-alerts') or {}).get('port', port) or 0)
        running = (report.get('plugins') or {}).get('librenms-alerts') or {}
        # The agent says whether it got a certificate (agent.py's tls gauge); unknown: HTTPS, the intent.
        scheme = 'http' if (running.get('metrics') or {}).get('tls') == 0 else 'https'
        agents.append({'id': a['id'], 'name': a['name'], 'connected': bool(a.get('connected')),
                       'url': f"{scheme}://{host or '<agent address>'}:{mine}{PATH}" if mine else '',
                       'address_known': bool(host), 'status': running.get('status'),
                       # Why it isn't listening, in the agent's words (a port taken, no token yet).
                       'problem': '' if running.get('status') in (None, 'ok') else (running.get('message') or '')})
    enabled = bool(registry is not None and registry.active('librenms-alerts'))
    return {'enabled': enabled, 'port': port, 'method': 'POST', 'content_type': 'application/json', 'body': BODY,
            'agents': agents, 'active': len(active(data))}
