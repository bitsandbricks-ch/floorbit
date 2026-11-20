"""Everything wrong right now, in one list (issue #10): see docs/alerts.md.

Gathered from what is already watched, without asking anything new:

- the monitoring source (LibreNMS) not answering;
- placed switches that are offline (from the status monitor), marked when their alerts are muted;
- red and amber services on the health wall;
- high and medium security findings (where only, unless the account has ``seats.view``);
- power circuits that tripped, are about to, or are getting close;
- the bandwidth forecast reaching the line's capacity within the next hours (floorbit/forecast.py);
- links between switches that are down or slower than planned (floorbit/links.py);
- Wi-Fi access points that are down or busy, and two near each other on one channel (floorbit/wifi.py);
- plugins turned on that don't load or keep failing, and installed versions the Marketplace withdrew.

Ports that need a look (issue #15: flapping, errors rising, half duplex, online without a check-in)
seats outside their switch's range (floorbit/seat_ranges.py), seat ports whose config breaks a
rule (floorbit/port_config.py) and seat ports with more than one machine on them
(floorbit/port_clients.py) come as a list of their own under
``attention``, newest first.

Each problem is ``{id, kind, level, title, where, since, link}`` with ``level`` ``down`` or ``warn``.
"""
import time
from urllib.parse import quote

from flask import current_app

from integrations import alerting

from . import sources

SECURITY_KINDS = {'rogue-dhcp': 'Rogue DHCP server', 'arp-spoof': 'ARP spoofing', 'mac-flap': 'MAC flapping',
                  'loop': 'Network loop', 'storm': 'Broadcast storm', 'other': 'Security finding'}


def _monitoring():
    health = sources.health()
    if not health.get('offline_since'):
        return []
    name = health.get('label') or health.get('source') or 'The monitoring source'
    agent = health.get('source') == 'agent'
    if health.get('last_ok') is None:
        # Never answered since the start: on a fresh install that is setup still to do, not an outage.
        return [{'id': 'monitoring', 'kind': 'monitoring', 'level': 'down', 'title': f'{name} has not answered yet',
                 'where': 'No switch status until it does', 'since': health['offline_since'],
                 'link': '/settings/agents' if agent else '/settings/plugins'}]
    return [{'id': 'monitoring', 'kind': 'monitoring', 'level': 'down', 'title': f'{name} is not answering',
             'where': 'Switch status is frozen at the last good data', 'since': health['offline_since'],
             'link': '/settings/agents' if agent else '/'}]


def _on_plan(seat=None, switch=None):
    """The floor plan opens the hall the seat or switch is in and selects it (issue #212)."""
    return f'/plan?seat={quote(seat)}' if seat else f'/plan?switch={quote(switch)}'


def _switches(muted):
    monitor = (current_app.extensions.get('floorbit_integrations') or {}).get('monitor')
    out = []
    for s in list(getattr(monitor, 'statuses', {}).values()):
        if s.get('status') != 'offline':
            continue
        mute = muted.get(s['id'])
        out.append({'id': f"switch:{s['id']}", 'kind': 'switch', 'level': 'down', 'title': f"{s['name']} is offline",
                    'where': s['name'], 'since': s.get('since'), 'link': _on_plan(switch=s['name']),
                    'switch_id': s['id'], 'mute_id': s['id'], 'name': s['name'], 'muted': _muted(mute)})
    return out


def _reach(items):
    """What each down switch or link cuts off (issue #950): its seats, by name only, and the switches
    behind it. A switch that is down only because the one before it is names that one as its
    ``cause``, so the crew starts at the cause."""
    from . import impact
    from .store import load_data
    switches = [p for p in items if p['kind'] == 'switch']
    down_links = [p['id'].split(':', 1)[1] for p in items
                  if p['kind'] == 'link' and p['id'].startswith('link:') and p['level'] == 'down']
    if not switches and not down_links:
        return
    found = impact.failures(load_data(), [p['name'] for p in switches], down_links)
    for p in switches:
        hit = found['switches'].get(p['name']) or {}
        p['seats'], p['behind'] = hit.get('seats') or [], hit.get('behind') or []
        cause = next((n for n, f in found['switches'].items()
                      if n != p['name'] and p['name'] in f['behind']), None)
        if cause:
            p['cause'] = cause
    for p in items:
        hit = found['links'].get(p['id'].split(':', 1)[1]) if p['kind'] == 'link' else None
        if hit:
            p['seats'], p['behind'] = hit['seats'], hit['behind']


def _muted(mute):
    return {'until': mute['until'], 'by': mute.get('by'), 'reason': mute.get('reason')} if mute else None


def _health(muted):
    wall = current_app.extensions.get('floorbit_health')
    out = []
    for c in (wall.snapshot()['checks'] if wall else []):
        if c['status'] in ('down', 'warn'):
            key = alerting.service_key(c['id'])
            out.append({'id': key, 'kind': 'health', 'level': c['status'],
                        'title': f"{c['name']}: {'down' if c['status'] == 'down' else 'needs a look'}",
                        'where': c.get('summary') or '', 'since': c.get('since'), 'link': '/services',
                        'mute_id': key, 'name': c['name'], 'muted': _muted(muted.get(key))})
    return out


def _security(may_see_people):
    watch = current_app.extensions.get('floorbit_security')
    out = []
    for f in (watch.snapshot()['findings'] if watch else []):
        if f['severity'] == 'low':
            continue
        port = ' '.join(x for x in (f.get('switch'), f.get('port')) if x)
        # Titles and seats can point at a person (IPs, MACs): only for seats.view.
        where = (f"Seat {f['seat']} ({port})" if f.get('seat') else port) if may_see_people else port
        out.append({'id': f"security:{f['id']}", 'kind': 'security',
                    'level': 'down' if f['severity'] == 'high' else 'warn',
                    'title': f['title'] if may_see_people else SECURITY_KINDS.get(f['kind'], 'Security finding'),
                    'where': where, 'since': f.get('first_seen'),
                    'link': '/security' if may_see_people else ''})
    return out


def _power():
    from . import power
    watch = current_app.extensions.get('floorbit_power')
    if not watch or not power.enabled():
        return []
    out = []
    for c in watch.snapshot()['circuits']:
        if c['state'] not in ('tripped', 'crit', 'warn'):
            continue
        title = {'tripped': f"Breaker tripped: {c['name']}",
                 'crit': f"Circuit {c['name']} about to trip ({c['load_pct']} %)",
                 'warn': f"Circuit {c['name']} getting close ({c['load_pct']} %)"}[c['state']]
        seats = len(c['fed']['seats'])
        feeds = ', '.join([f"{seats} seat{'s' if seats != 1 else ''}"] * bool(seats) +
                          [s['name'] for s in c['fed']['switches']])
        since = (c.get('tripped') or {}).get('at') if c['state'] == 'tripped' else (c.get('reading') or {}).get('at')
        out.append({'id': f"power:{c['id']}", 'kind': 'power', 'level': 'warn' if c['state'] == 'warn' else 'down',
                    'title': title, 'where': f'Feeds {feeds}' if feeds else '', 'since': since, 'link': '/power'})
    return out


def _forecast():
    from . import features
    watch = current_app.extensions.get('floorbit_forecast')
    if not watch or not features.on('forecast'):
        return []
    alert = (watch.last or {}).get('alert')
    if not alert or alert['t'] < time.time() - 3600:
        return []
    at = time.strftime('%H:%M', time.localtime(alert['t']))
    return [{'id': f"forecast:{alert['t']}", 'kind': 'forecast', 'level': 'down' if alert['pct'] >= 100 else 'warn',
             'title': f"Bandwidth expected at {alert['pct']} % of the line around {at}",
             'where': 'Forecast from the hours so far', 'since': None, 'link': '/overview'}]


def _attention():
    watch = current_app.extensions.get('floorbit_attention')
    out = []
    for a in (watch.snapshot()['items'] if watch else []):
        link = _on_plan(seat=a.get('seat'), switch=a.get('switch') or a['switch_id'])
        out.append({'id': f"attention:{a['id']}", 'kind': a['kind'], 'level': 'warn', 'title': a['title'],
                    'where': a['where'], 'since': a['since'], 'link': link, 'switch_id': a['switch_id']})
    return out


def _ranges():
    """Seats with an address outside their switch's ranges (floorbit/seat_ranges.py, issue #1062)."""
    from integrations import seat_sources

    from . import seat_ranges
    from .store import load_data
    try:
        found = seat_ranges.items(load_data(), seat_sources.load())
    except Exception:  # noqa: BLE001 - a seat source that can't be read must not take the page down
        return []
    # A range set for the wrong switch is fixed under Firewalls; the rest on the plan.
    return [{'id': f['id'], 'kind': 'range', 'level': 'warn', 'title': f['title'], 'where': f['where'],
             'since': None, 'switch_id': None,
             'link': '/firewalls' if f['id'].startswith('range:plan:')
             else _on_plan(seat=f['seat'], switch=f['switch'])}
            for f in found]


def _port_check():
    """Seat ports whose config breaks a rule, from the last config copies (floorbit/port_config.py)."""
    from integrations import seat_sources

    from . import port_config
    from .store import load_data
    try:
        found = port_config.problems(port_config.check(load_data(), seat_sources.load()))
    except Exception:  # noqa: BLE001 - a copy or seat source that can't be read must not take the page down
        return []
    return [{'id': f['id'], 'kind': 'portconfig', 'level': 'warn', 'title': f['title'], 'where': f['where'],
             'since': None, 'switch_id': None, 'link': '/configs#port-check'} for f in found]


def _shared_ports():
    """Seat ports with more than one machine, from the last MAC table read (floorbit/port_clients.py)."""
    from . import port_clients
    state = port_clients.last_read()
    if not state:
        return []
    return [{'id': f['id'], 'kind': 'shared', 'level': 'warn', 'title': f['title'], 'where': f['where'],
             'since': None, 'switch_id': None,
             'link': _on_plan(seat=f['seat'], switch=f['switch']) if f['seat'] else '/cables#port-clients'}
            for f in port_clients.problems(state)]


def _logs(may_see_people):
    """Syslog lines that matched a known pattern (floorbit/log_alerts.py), as port trouble."""
    from . import features, inventory
    from .store import load_data
    receiver = current_app.extensions.get('floorbit_syslog')
    if not receiver or not features.on('syslog'):
        return []
    by_name = {d['name'].lower(): d['id'] for d in inventory.devices(load_data())}
    out = []
    for a in receiver.alert_items():
        switch_id = by_name.get(a['device'].lower())
        where = ' '.join(x for x in (a['device'], a['port']) if x) + (f" (seat {a['seat']})" if a['seat'] else '')
        title = a['title'] + (f" ({a['count']} lines)" if a['count'] > 1 else '')
        if may_see_people:
            query = f"seat={quote(a['seat'])}" if a['seat'] else f"device={quote(a['device'])}"
            link = f'/logs?{query}'
        else:
            link = _on_plan(seat=a['seat'], switch=a['device']) if a['seat'] or switch_id else ''
        out.append({'id': a['id'], 'kind': 'log', 'level': 'warn', 'title': title, 'where': where,
                    'since': a['since'], 'link': link, 'switch_id': switch_id})
    return out


PLUGIN_FAILING_FOR = 300   # seconds of failed calls before a plugin is a problem: one timeout isn't


def _plugins():
    """Plugins turned on that don't load, whose calls have failed for PLUGIN_FAILING_FOR, or
    that run a version the Marketplace withdrew."""
    from . import marketplace
    registry = current_app.extensions.get('floorbit_plugins')
    if registry is None:
        return []
    now, out = time.time(), []
    for spec in sorted(registry.specs.values(), key=lambda s: s.id):
        if spec.error and registry.wanted(spec):
            out.append({'id': f'plugin:load:{spec.id}', 'kind': 'plugin', 'level': 'down',
                        'title': f'{spec.name} does not load', 'where': spec.error[:300], 'since': None,
                        'link': f'/settings/plugins/{quote(spec.id)}'})
    for pid, (since, message) in sorted(registry.failing().items()):
        spec = registry.specs.get(pid)
        if spec is None or not registry.enabled(spec) or now - since < PLUGIN_FAILING_FOR:
            continue
        out.append({'id': f'plugin:failing:{pid}', 'kind': 'plugin', 'level': 'warn',
                    'title': f'{spec.name} keeps failing', 'where': message, 'since': since,
                    'link': f'/settings/plugins/{quote(pid)}'})
    try:
        withdrawn = marketplace.withdrawn_running()
    except Exception:  # noqa: BLE001  # the database or the folder being away is not Problems' to report here
        withdrawn = []
    for pid, version, why in withdrawn:
        name = registry.specs[pid].name if pid in registry.specs else pid
        out.append({'id': f'plugin:withdrawn:{pid}:{version}', 'kind': 'plugin', 'level': 'warn',
                    'title': f'{name} {version} was withdrawn', 'where': why, 'since': None,
                    'link': '/settings/plugins?tab=updates'})
    return out


def _mute_kind(key):
    return 'health' if key.startswith(alerting.service_key('')) else 'wifi' if key.startswith('wifi:') else 'switch'


def _wifi(muted):
    from . import features, wifi
    from .store import load_data
    data = load_data()
    registry = current_app.extensions.get('floorbit_plugins')
    if registry is None or not features.on('wifi', data) or not (registry.feeders('wifi') or wifi.agent_active()):
        return []
    return wifi.problems(registry, data, muted)


def current(may_see_people):
    muted = alerting.mutes()
    from . import links
    items = (_monitoring() + _switches(muted) + _health(muted) + _security(may_see_people) + _power() + _forecast()
             + links.problems() + _wifi(muted) + _plugins())
    _reach(items)
    now = time.time()
    items.sort(key=lambda p: (p['level'] != 'down', bool(p.get('muted')), p.get('since') or now))
    counts = {'down': sum(p['level'] == 'down' and not p.get('muted') for p in items),
              'warn': sum(p['level'] == 'warn' and not p.get('muted') for p in items),
              'muted': sum(bool(p.get('muted')) for p in items)}
    # Port trouble is its own list, newest first: during an event there can be dozens, and they
    # shouldn't bury a switch that is down.
    attention = sorted(_attention() + _logs(may_see_people) + _ranges() + _port_check()
                       + _shared_ports(),
                       key=lambda p: -(p['since'] or 0))
    counts['attention'] = len(attention)
    mutes = [{'switch_id': k, 'kind': _mute_kind(k), **v}
             for k, v in sorted(muted.items(), key=lambda kv: kv[1]['until'])]
    return {'problems': items, 'attention': attention, 'counts': counts, 'mutes': mutes,
            'quiet_hours': alerting.quiet_now(), 'checked_at': now}
