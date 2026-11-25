"""Everything wrong right now, in one list (issue #10): see docs/alerts.md.

Gathered from what is already watched, without asking anything new:

- the monitoring source (LibreNMS) not answering;
- placed switches that are offline (from the status monitor), marked when their alerts are muted;
- red and amber services on the health wall;
- high and medium security findings (where only, unless the account has ``seats.view``); low ones
  go under ``attention``;
- power circuits that tripped, are about to, or are getting close;
- the bandwidth forecast reaching the line's capacity within the next hours (floorbit/forecast.py);
- links between switches that are down or slower than planned (floorbit/links.py);
- Wi-Fi access points that are down or busy, and two near each other on one channel (floorbit/wifi.py);
- plugins turned on that don't load or keep failing, and installed versions the Marketplace withdrew;
- alerts LibreNMS pushed through the agent (floorbit/librenms_alerts.py).

Seat and port trouble (issue #15: flapping, errors rising, half duplex, online without a check-in;
syslog matches; seats outside their switch's range, floorbit/seat_ranges.py; seat ports whose config
breaks a rule, floorbit/port_config.py; seat ports with more than one machine, floorbit/port_clients.py;
open incidents on a seat, issue #1204; addresses that send syslog or flows but aren't in the inventory,
floorbit/unknown_senders.py) comes as a list of its own under ``attention``, newest first,
each with its ``seat`` when it has one. The page shows it with the rest, after it; ``counts['seats']``
is how many seats have trouble, counted like the floor plan's "!" (check-in left out).

Each problem is ``{id, kind, level, title, where, since, link, device}`` with ``level`` ``down`` or ``warn``;
``device`` is the switch it is on, when it is on one.

Each also carries (issue #1364) a ``priority``: 1 when it is down and cuts off more than itself (a
switch or link with switches behind it or with ``MANY_SEATS`` seats or more, or a router, firewall,
core or distribution box), 2 for the
rest that is down, 3 for everything to look at. Someone working the problems can raise one to 1 by
hand (``raised``: who, when), stored under ``problem_raised``. ``hall`` is the hall its switch or seat
is in and ``tags`` its switch's tags, so the page can group and filter by them.
"""
import threading
import time
from urllib.parse import quote

from flask import current_app

from integrations import alerting

from . import sources, unknown_senders

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


def _reach(items, data):
    """What each down switch or link cuts off (issue #950): its seats, by name only, and the switches
    behind it. A switch that is down only because the one before it is names that one as its
    ``cause``, so the crew starts at the cause."""
    from . import impact
    switches = [p for p in items if p['kind'] == 'switch']
    down_links = [p['id'].split(':', 1)[1] for p in items
                  if p['kind'] == 'link' and p['id'].startswith('link:') and p['level'] == 'down']
    if not switches and not down_links:
        return
    found = impact.failures(data, [p['name'] for p in switches], down_links)
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
            full_in = (c.get('forecast') or {}).get('full_in_min')
            title = (f"{c['name']}: full in about {full_in} min" if full_in and c['status'] == 'warn'
                     else f"{c['name']}: {'down' if c['status'] == 'down' else 'needs a look'}")
            out.append({'id': key, 'kind': 'health', 'level': c['status'],
                        'title': title,
                        'where': c.get('summary') or '', 'since': c.get('since'), 'link': '/services',
                        'mute_id': key, 'name': c['name'], 'muted': _muted(muted.get(key))})
    return out


def _security(may_see_people, low=False):
    """High and medium findings are problems; low ones go with the seat and port trouble (``low``).
    The finding itself (evidence, shutting its port) is on the problem's page (issue #885)."""
    watch = current_app.extensions.get('floorbit_security')
    out = []
    for f in (watch.snapshot()['findings'] if watch else []):
        if (f['severity'] == 'low') != low:
            continue
        port = ' '.join(x for x in (f.get('switch'), f.get('port')) if x)
        # Titles and seats can point at a person (IPs, MACs): only for seats.view.
        where = (f"Seat {f['seat']} ({port})" if f.get('seat') else port) if may_see_people else port
        out.append({'id': f"security:{f['id']}", 'kind': 'security',
                    'level': 'down' if f['severity'] == 'high' else 'warn',
                    'title': f['title'] if may_see_people else SECURITY_KINDS.get(f['kind'], 'Security finding'),
                    'where': where, 'since': f.get('first_seen'), 'link': '',
                    'seat': f.get('seat') if may_see_people else None, 'device': f.get('switch') or None})
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
             'where': 'Forecast from the hours so far', 'since': None, 'link': '/stats'}]


def _attention():
    watch = current_app.extensions.get('floorbit_attention')
    out = []
    for a in (watch.snapshot()['items'] if watch else []):
        link = _on_plan(seat=a.get('seat'), switch=a.get('switch') or a['switch_id'])
        out.append({'id': f"attention:{a['id']}", 'kind': a['kind'], 'level': 'warn', 'title': a['title'],
                    'where': a['where'], 'since': a['since'], 'link': link, 'switch_id': a['switch_id'],
                    'seat': a.get('seat')})
    return out


def _seat_incidents():
    """Open incidents on a seat: the floor plan marks those seats, so Problems lists them too (issue #1204)."""
    from . import incidents
    out = []
    for i in incidents.list_all():
        if i.get('status') == 'fixed' or not i.get('seat'):
            continue
        out.append({'id': f"incident:{i['id']}", 'kind': 'incident', 'level': 'warn', 'title': i['title'],
                    'where': f"Seat {i['seat']}, on the incident board", 'since': i.get('created_at'),
                    'link': f"/incidents?q={quote('seat:' + i['seat'])}", 'seat': i['seat']})
    return out


def _ranges(data):
    """Seats with an address outside their switch's ranges (floorbit/seat_ranges.py, issue #1062)."""
    from integrations import seat_sources

    from . import seat_ranges
    try:
        found = seat_ranges.items(data, seat_sources.load())
    except Exception:  # noqa: BLE001 - a seat source that can't be read must not take the page down
        return []
    # A range set for the wrong switch is fixed under Firewalls; the rest on the plan.
    return [{'id': f['id'], 'kind': 'range', 'level': 'warn', 'title': f['title'], 'where': f['where'],
             'since': None, 'switch_id': None, 'device': f.get('switch') or None,
             'link': '/firewalls' if f['id'].startswith('range:plan:')
             else _on_plan(seat=f['seat'], switch=f['switch'])}
            for f in found]


def _port_check(data):
    """Seat ports whose config breaks a rule, from the last config copies (floorbit/port_config.py)."""
    from integrations import seat_sources

    from . import port_config
    try:
        found = port_config.problems(port_config.check(data, seat_sources.load()))
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
             'since': None, 'switch_id': None, 'device': f.get('switch') or None,
             'link': _on_plan(seat=f['seat'], switch=f['switch']) if f['seat'] else '/cables#port-clients'}
            for f in port_clients.problems(state)]


def _logs(may_see_people, data):
    """Syslog lines that matched a known pattern (floorbit/log_alerts.py), as port trouble."""
    from . import features, inventory
    receiver = current_app.extensions.get('floorbit_syslog')
    if not receiver or not features.on('syslog'):
        return []
    by_name = {d['name'].lower(): d['id'] for d in inventory.devices(data)}
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
                    'since': a['since'], 'link': link, 'switch_id': switch_id, 'seat': a['seat'] or None})
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
    if key.startswith(PROBLEM_MUTE):
        return 'problem'
    return 'health' if key.startswith(alerting.service_key('')) else 'wifi' if key.startswith('wifi:') else 'switch'


# Every other problem is muted by its own id (issue #887): it stays on the list, marked, and leaves
# the counts until the mute ends. Switches, services and access points keep their own keys, which
# also quiet their Discord messages.
PROBLEM_MUTE = 'problem:'


def _mute_rest(items, muted):
    for p in items:
        if not p.get('mute_id') and p['kind'] != 'switch':
            p['mute_id'] = PROBLEM_MUTE + p['id']
            p['muted'] = _muted(muted.get(p['mute_id']))


RAISED = 'problem_raised'
# A raise is for this event's trouble: one older than this is forgotten.
RAISED_KEEP = 7 * 24 * 3600
# Boxes that carry more than one row of seats: down, they come first even with nothing mapped behind them.
UPLINK_ROLES = ('router', 'firewall', 'core', 'distribution')
# An access switch that takes this many seats with it is urgent too (Mike, 2026-11-25).
MANY_SEATS = 20
_raise_lock = threading.Lock()


def raised(data, now=None):
    now = now or time.time()
    return {k: v for k, v in (data.get(RAISED) or {}).items()
            if isinstance(v, dict) and float(v.get('at') or 0) > now - RAISED_KEEP}


def set_raised(problem_id, user, on=True):
    """Raise a problem to priority 1, or take that back. Returns whether anything changed."""
    from .store import load_data, save_data
    now = time.time()
    with _raise_lock:
        data = load_data()
        kept = raised(data, now)
        if on == (problem_id in kept):
            return False
        if on:
            kept[problem_id] = {'by': user, 'at': now}
        else:
            kept.pop(problem_id)
        data[RAISED] = kept
        save_data(data)
    return True


def _place(items, data):
    """Hall, tags and priority of each problem (issue #1364)."""
    from . import halls, inventory
    from .seat_names import block_rows
    devices = inventory.devices(data, include_hidden=True)
    hall_ids = {h['id'] for h in halls.halls(data)}
    hall_names = {h['id']: h.get('name') or h['id'] for h in halls.halls(data)}
    by_id = {d['id']: d for d in devices}
    by_name = {str(d.get('name') or '').lower(): d for d in devices}
    seat_hall = {}
    for block in data.get('seat_blocks') or []:
        hid = halls.hall_of(block, data, hall_ids)
        for row in block_rows(block):
            for seat in row:
                seat_hall[seat] = hid
    ups = raised(data)
    for p in items:
        dev = by_id.get(p.get('switch_id')) or by_name.get(str(p.get('device') or '').lower())
        hid = halls.hall_of(dev, data, hall_ids) if dev else seat_hall.get(p.get('seat'))
        p['hall'] = hall_names.get(hid) if hid else None
        p['tags'] = list(dev.get('tags') or []) if dev else []
        wide = (bool(p.get('behind')) or len(p.get('seats') or []) >= MANY_SEATS
                or bool(dev and str(dev.get('role') or '').lower() in UPLINK_ROLES))
        p['priority'] = (1 if wide else 2) if p['level'] == 'down' else 3
        up = ups.get(p['id'])
        p['raised'] = {'by': up.get('by'), 'at': up['at']} if up else None
        if up:
            p['priority'] = 1


def _wifi(muted, data):
    from . import features, wifi
    registry = current_app.extensions.get('floorbit_plugins')
    if registry is None or not features.on('wifi', data) or not (registry.feeders('wifi') or wifi.agent_active()):
        return []
    return wifi.problems(registry, data, muted)


def current(may_see_people):
    from . import librenms_alerts, links
    from .store import load_data
    # Read once and handed on: every page asks for this, and each part reading data.json itself
    # parsed it a dozen times per request.
    data = load_data()
    muted = alerting.mutes(data=data)
    items = (_monitoring() + _switches(muted) + _health(muted) + _security(may_see_people) + _power() + _forecast()
             + links.problems(data) + _wifi(muted, data) + _plugins() + librenms_alerts.problems(data))
    _reach(items, data)
    _mute_rest(items, muted)
    now = time.time()
    counts = {'down': sum(p['level'] == 'down' and not p.get('muted') for p in items),
              'warn': sum(p['level'] == 'warn' and not p.get('muted') for p in items),
              'muted': sum(bool(p.get('muted')) for p in items)}
    # Port trouble is its own list, newest first: during an event there can be dozens, and they
    # shouldn't bury a switch that is down.
    attention = sorted(_attention() + _logs(may_see_people, data) + _ranges(data) + _port_check(data)
                       + _shared_ports() + _seat_incidents() + _security(may_see_people, low=True)
                       + unknown_senders.problems(data),
                       key=lambda p: -(p['since'] or 0))
    _mute_rest(attention, muted)
    attention.sort(key=lambda p: bool(p.get('muted')))
    counts['attention'] = sum(not p.get('muted') for p in attention)
    counts['muted'] += len(attention) - counts['attention']
    # The switch each one is on, so the page can group by it (issue #883).
    from . import inventory
    names = {d['id']: d['name'] for d in inventory.devices(data, include_hidden=True)}
    for p in items + attention:
        p.setdefault('device', p.get('name') if p['kind'] == 'switch' else names.get(p.get('switch_id')))
    _place(items + attention, data)
    # Most urgent first (issue #1364); a raised one with them, muted ones last.
    items.sort(key=lambda p: (bool(p.get('muted')), p['priority'], p.get('since') or now))
    attention.sort(key=lambda p: (bool(p.get('muted')), p['priority']))   # stable: newest first within
    # One count for every place that shows one (#884): the sidebar shows `down`, the footer `down`
    # and `look`, the bell, tab titles and the handover `total`; seat and port trouble is a look too.
    counts['look'] = counts['warn'] + counts['attention']
    counts['total'] = counts['down'] + counts['look']
    counts['seats'] = len({p['seat'] for p in items + attention
                           if p.get('seat') and p['kind'] != 'checkin' and not p.get('muted')})
    mutes = [{'switch_id': k, 'kind': _mute_kind(k), **v}
             for k, v in sorted(muted.items(), key=lambda kv: kv[1]['until'])]
    return {'problems': items, 'attention': attention, 'counts': counts, 'mutes': mutes,
            'quiet_hours': alerting.quiet_now(), 'checked_at': now}


def find(may_see_people, problem_id):
    """One problem as the list shows it, or None once it is over (issue #882)."""
    body = current(may_see_people)
    return next((p for p in body['problems'] + body['attention'] if p['id'] == problem_id), None)
