"""Everything wrong right now, in one list (issue #10): see docs/alerts.md.

Gathered from what is already watched, without asking anything new:

- the monitoring source (LibreNMS) not answering;
- placed switches that are offline (from the status monitor), marked when their alerts are muted;
- red and amber services on the health wall;
- high and medium security findings (where only, unless the account has ``seats.view``);
- power circuits that tripped, are about to, or are getting close;
- the bandwidth forecast reaching the line's capacity within the next hours (floorbit/forecast.py).

Ports that need a look (issue #15: flapping, errors rising, half duplex, online without a check-in)
come as a list of their own under ``attention``, newest first.

Each problem is ``{id, kind, level, title, where, since, link}`` with ``level`` ``down`` or ``warn``.
"""
import time

from flask import current_app

from integrations import alerting

from . import sources

SECURITY_KINDS = {'rogue-dhcp': 'Rogue DHCP server', 'arp-spoof': 'ARP spoofing', 'mac-flap': 'MAC flapping',
                  'loop': 'Network loop', 'storm': 'Broadcast storm', 'other': 'Security finding'}


def _monitoring():
    health = sources.health()
    if health.get('offline_since'):
        return [{'id': 'monitoring', 'kind': 'monitoring', 'level': 'down',
                 'title': f"{health.get('source') or 'The monitoring source'} is not answering",
                 'where': 'Switch status is frozen at the last good data', 'since': health['offline_since'],
                 'link': '/'}]
    return []


def _switches(muted):
    monitor = (current_app.extensions.get('lal_integrations') or {}).get('monitor')
    out = []
    for s in list(getattr(monitor, 'statuses', {}).values()):
        if s.get('status') != 'offline':
            continue
        mute = muted.get(s['id'])
        out.append({'id': f"switch:{s['id']}", 'kind': 'switch', 'level': 'down', 'title': f"{s['name']} is offline",
                    'where': s['name'], 'since': s.get('since'), 'link': '/', 'switch_id': s['id'],
                    'muted': {'until': mute['until'], 'by': mute.get('by'), 'reason': mute.get('reason')}
                    if mute else None})
    return out


def _health():
    wall = current_app.extensions.get('floorbit_health')
    out = []
    for c in (wall.snapshot()['checks'] if wall else []):
        if c['status'] in ('down', 'warn'):
            out.append({'id': f"health:{c['id']}", 'kind': 'health', 'level': c['status'],
                        'title': f"{c['name']}: {'down' if c['status'] == 'down' else 'needs a look'}",
                        'where': c.get('summary') or '', 'since': c.get('since'), 'link': '/health'})
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
             'where': 'Forecast from the hours so far', 'since': None, 'link': '/stats'}]


def _attention():
    from urllib.parse import quote

    from .tournament import match_seats
    watch = current_app.extensions.get('floorbit_attention')
    match = match_seats()
    out = []
    for a in (watch.snapshot()['items'] if watch else []):
        link = f"/?seat={quote(a['seat'])}" if a.get('seat') else f"/?switch={quote(a['switch_id'])}"
        out.append({'id': f"attention:{a['id']}", 'kind': a['kind'], 'level': 'warn', 'title': a['title'],
                    'where': a['where'], 'since': a['since'], 'link': link, 'switch_id': a['switch_id'],
                    'match': match.get(a.get('seat') or '')})
    return out


def current(may_see_people):
    muted = alerting.mutes()
    items = _monitoring() + _switches(muted) + _health() + _security(may_see_people) + _power() + _forecast()
    now = time.time()
    items.sort(key=lambda p: (p['level'] != 'down', bool(p.get('muted')), p.get('since') or now))
    counts = {'down': sum(p['level'] == 'down' and not p.get('muted') for p in items),
              'warn': sum(p['level'] == 'warn' for p in items),
              'muted': sum(bool(p.get('muted')) for p in items)}
    # Port trouble is its own list, newest first: during an event there can be dozens, and they
    # shouldn't bury a switch that is down.
    # Match seats (issue #31) first: a tournament player losing their link can't wait.
    attention = sorted(_attention(), key=lambda p: (not p.get('match'), -(p['since'] or 0)))
    counts['match'] = sum(bool(p.get('match')) for p in attention)
    counts['attention'] = len(attention)
    mutes = [{'switch_id': k, **v} for k, v in sorted(muted.items(), key=lambda kv: kv[1]['until'])]
    return {'problems': items, 'attention': attention, 'counts': counts, 'mutes': mutes,
            'quiet_hours': alerting.quiet_now(), 'checked_at': now}
