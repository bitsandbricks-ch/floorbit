"""Floorbit's own dashboard tiles (issue #302): problems and incidents, with no plugin installed.

They come as ordinary widget tiles from the plugin id ``floorbit`` (which no plugin may take), so
layouts, the wall view and the widget renderer treat them like any plugin's. Texts follow the
browser's language, like the other pages the server writes text for.
"""
import time

PLUGIN = 'floorbit'
NAME = 'Floorbit'

TEXTS = {
    'en': {'problems': 'Problems right now', 'incidents': 'Incidents', 'down': 'down', 'open': 'open',
           'switches': 'Switches', 'switches_unit': 'of {n} up',
           'switches_sub': '{offline} offline · {unknown} not known',
           'seats': 'Seats online', 'seats_unit': 'of {n}', 'seats_sub': 'From the last port read',
           'unknown': 'Not known right now: no recent port read',
           'problems_sub': '{warn} to look at · {attention} port trouble · {muted} muted',
           'incidents_sub': '{waiting} waiting 10+ min · {worked} being worked',
           'down_switches': 'Switches down', 'all_up': 'All switches up', 'no_status': 'No switch status yet',
           'just_now': 'just now', 'mins': '{n} min', 'hours': '{h} h {m} min', 'more': '+ {n} more',
           'switch_states': 'Switch states', 'down_for': 'down {t}', 'open_incidents': 'Open incidents',
           'col_what': 'What', 'col_where': 'Where', 'col_open': 'Open for', 'switch_at': 'Switch {name}',
           'seat_at': 'Seat {seat}', 'traffic': 'Traffic', 'download': 'Download', 'upload': 'Upload',
           'seats_by_block': 'Seats online by block',
           'bandwidth': 'Bandwidth', 'down_up': '↓ {down} · ↑ {up}', 'no_reads': 'No traffic read yet',
           'peak': 'Peak of the event', 'peak_sub': '{ago} ago · 24 h peak {day}', 'ports': 'Ports',
           'ports_unit': 'up', 'ports_sub': '{down} down · {errors} with errors', 'uplinks': 'Uplinks',
           'top_ports': 'Busiest seats', 'port_at': '{switch} {port}', 'traffic_mix': 'Traffic by kind',
           'mix_sub': 'Last hour: {total}', 'flow_services': 'Top services', 'seat_count': '{n} seats',
           'traffic_areas': 'Traffic by area', 'anomalies': 'Look at this', 'nothing_odd': 'Nothing odd',
           'for': 'for {t}', 'no_flows': 'No flows yet',
           'service_health': 'Service health', 'no_checks': 'Nothing checked yet',
           'internet_uplinks': 'Internet uplinks', 'in_out': '{pct} % · ↓ {down} · ↑ {up}', 'link_down': 'down',
           'lancache': 'LAN cache', 'lancache_sub': '{hit} from the cache · {miss} from the internet',
           'no_cache': 'No LAN cache set up', 'power_circuits': 'Power load', 'tripped': 'tripped',
           'no_circuits': 'No circuits set up', 'agents': 'Agents', 'agents_unit': 'of {n} online',
           'agents_sub': '{outdated} need an update', 'no_agents': 'No agent yet',
           'dns_lookups': 'DNS lookups', 'dns_sub': '{blocked} blocked ({share} %) in {hours} h',
           'no_dns': 'No DNS logs yet', 'dns_sites': 'Top sites', 'dns_blocked': 'Blocked sites',
           'lookups': '{n} lookups', 'launchers': 'Game launchers',
           'launcher_value': '{cache} from the cache · {seats} seats',
           'launcher_cache': '{cache} from the cache', 'no_games': 'No game traffic yet',
           'wifi_clients': 'Wi-Fi clients', 'wifi_sub': '2.4 GHz: {b24} · 5 GHz: {b5}', 'no_wifi': 'No Wi-Fi data yet',
           'wifi_aps': 'Access points', 'ap_clients': '{n} clients', 'busy': 'busy',
           'cat': {'gaming': 'Gaming', 'streaming': 'Streaming', 'downloads': 'Downloads', 'updates': 'Updates',
                   'web': 'Web', 'other': 'Other'}},
    'de': {'problems': 'Probleme jetzt', 'incidents': 'Störungen', 'down': 'ausgefallen', 'open': 'offen',
           'switches': 'Switches', 'switches_unit': 'von {n} online',
           'switches_sub': '{offline} offline · {unknown} unbekannt',
           'seats': 'Plätze online', 'seats_unit': 'von {n}', 'seats_sub': 'Aus der letzten Port-Abfrage',
           'unknown': 'Gerade nicht bekannt: keine aktuelle Port-Abfrage',
           'problems_sub': '{warn} zum Anschauen · {attention} Port-Probleme · {muted} stumm',
           'incidents_sub': '{waiting} warten seit 10+ Min. · {worked} in Arbeit',
           'down_switches': 'Switches ausgefallen', 'all_up': 'Alle Switches online',
           'no_status': 'Noch kein Switch-Status', 'just_now': 'gerade eben', 'mins': '{n} Min.',
           'hours': '{h} Std. {m} Min.', 'more': '+ {n} weitere',
           'switch_states': 'Switch-Status', 'down_for': 'aus seit {t}', 'open_incidents': 'Offene Störungen',
           'col_what': 'Was', 'col_where': 'Wo', 'col_open': 'Offen seit', 'switch_at': 'Switch {name}',
           'seat_at': 'Platz {seat}', 'traffic': 'Verkehr', 'download': 'Download', 'upload': 'Upload',
           'seats_by_block': 'Plätze online nach Block',
           'bandwidth': 'Bandbreite', 'down_up': '↓ {down} · ↑ {up}', 'no_reads': 'Noch keine Verkehrsdaten',
           'peak': 'Spitze des Events', 'peak_sub': 'vor {ago} · 24-Std.-Spitze {day}', 'ports': 'Ports',
           'ports_unit': 'online', 'ports_sub': '{down} offline · {errors} mit Fehlern', 'uplinks': 'Uplinks',
           'top_ports': 'Aktivste Plätze', 'port_at': '{switch} {port}', 'traffic_mix': 'Verkehr nach Art',
           'mix_sub': 'Letzte Stunde: {total}', 'flow_services': 'Top-Dienste', 'seat_count': '{n} Plätze',
           'traffic_areas': 'Verkehr nach Bereich', 'anomalies': 'Anschauen', 'nothing_odd': 'Nichts Auffälliges',
           'for': 'seit {t}', 'no_flows': 'Noch keine Flows',
           'service_health': 'Dienst-Status', 'no_checks': 'Noch nichts geprüft',
           'internet_uplinks': 'Internet-Uplinks', 'in_out': '{pct} % · ↓ {down} · ↑ {up}', 'link_down': 'offline',
           'lancache': 'LAN-Cache', 'lancache_sub': '{hit} aus dem Cache · {miss} aus dem Internet',
           'no_cache': 'Kein LAN-Cache eingerichtet', 'power_circuits': 'Stromlast', 'tripped': 'ausgelöst',
           'no_circuits': 'Keine Stromkreise eingerichtet', 'agents': 'Agenten', 'agents_unit': 'von {n} online',
           'agents_sub': '{outdated} brauchen ein Update', 'no_agents': 'Noch kein Agent',
           'dns_lookups': 'DNS-Anfragen', 'dns_sub': '{blocked} blockiert ({share} %) in {hours} Std.',
           'no_dns': 'Noch keine DNS-Logs', 'dns_sites': 'Top-Sites', 'dns_blocked': 'Blockierte Sites',
           'lookups': '{n} Anfragen', 'launchers': 'Game-Launcher',
           'launcher_value': '{cache} aus dem Cache · {seats} Plätze',
           'launcher_cache': '{cache} aus dem Cache', 'no_games': 'Noch kein Game-Verkehr',
           'wifi_clients': 'WLAN-Clients', 'wifi_sub': '2.4 GHz: {b24} · 5 GHz: {b5}',
           'no_wifi': 'Noch keine WLAN-Daten',
           'wifi_aps': 'Access Points', 'ap_clients': '{n} Clients', 'busy': 'ausgelastet',
           'cat': {'gaming': 'Gaming', 'streaming': 'Streaming', 'downloads': 'Downloads', 'updates': 'Updates',
                   'web': 'Web', 'other': 'Anderes'}},
}
# One line per tile: its id, the text key of its label, its size and how often it reloads (seconds).
# blueprints/plugins.py core_widget() has the matching builder. The Widgets gallery lists them all.
TILES = {
    'problems': {'label': 'problems', 'size': 'small', 'refresh': 30},
    'incidents': {'label': 'incidents', 'size': 'small', 'refresh': 30},
    'switches': {'label': 'switches', 'size': 'small', 'refresh': 30},    # #304
    'seats': {'label': 'seats', 'size': 'small', 'refresh': 30},          # #304
    'down': {'label': 'down_switches', 'size': 'small', 'refresh': 15},  # the old /kiosk's "Down" list
    # Data for the generic widget types (#894): a state per switch, the open incidents, traffic over time.
    'switch_states': {'label': 'switch_states', 'size': 'small', 'refresh': 15},
    'open_incidents': {'label': 'open_incidents', 'size': 'small', 'refresh': 30},
    'traffic': {'label': 'traffic', 'size': 'wide', 'refresh': 30},
    'seats_by_block': {'label': 'seats_by_block', 'size': 'small', 'refresh': 30},
    # What the Stats and Traffic views showed in one big pane, as tiles of their own.
    'bandwidth': {'label': 'bandwidth', 'size': 'small', 'refresh': 30},
    'peak': {'label': 'peak', 'size': 'small', 'refresh': 30},
    'ports': {'label': 'ports', 'size': 'small', 'refresh': 30},
    'uplinks': {'label': 'uplinks', 'size': 'small', 'refresh': 30},
    'top_ports': {'label': 'top_ports', 'size': 'small', 'refresh': 30},
    'traffic_mix': {'label': 'traffic_mix', 'size': 'small', 'refresh': 30, 'feature': 'traffic'},
    'flow_services': {'label': 'flow_services', 'size': 'small', 'refresh': 30, 'feature': 'traffic'},
    'traffic_areas': {'label': 'traffic_areas', 'size': 'small', 'refresh': 30, 'feature': 'traffic'},
    'anomalies': {'label': 'anomalies', 'size': 'small', 'refresh': 30, 'feature': 'traffic'},
    # And what the Service health, Services, LAN cache, Power load and Agents views showed (#1045).
    'service_health': {'label': 'service_health', 'size': 'small', 'refresh': 15, 'feature': 'health'},
    'internet_uplinks': {'label': 'internet_uplinks', 'size': 'small', 'refresh': 30},
    'lancache': {'label': 'lancache', 'size': 'small', 'refresh': 60},
    'power_circuits': {'label': 'power_circuits', 'size': 'small', 'refresh': 30, 'feature': 'power'},
    'agents': {'label': 'agents', 'size': 'small', 'refresh': 30},
    # DNS, games and Wi-Fi (#1045): hall-wide numbers only, as on their pages.
    'dns_lookups': {'label': 'dns_lookups', 'size': 'small', 'refresh': 60, 'feature': 'dns'},
    'dns_sites': {'label': 'dns_sites', 'size': 'small', 'refresh': 60, 'feature': 'dns'},
    'dns_blocked': {'label': 'dns_blocked', 'size': 'small', 'refresh': 60, 'feature': 'dns'},
    'launchers': {'label': 'launchers', 'size': 'small', 'refresh': 60, 'feature': 'games'},
    'wifi_clients': {'label': 'wifi_clients', 'size': 'small', 'refresh': 30, 'feature': 'wifi'},
    'wifi_aps': {'label': 'wifi_aps', 'size': 'small', 'refresh': 30, 'feature': 'wifi'},
}
MAX_DOWN = 20   # a big screen reads a short list; the rest is "+ n more"


def tiles(lang, may_see_board, feature_on=lambda f: True):
    """The tile list entries, next to the plugins' in ``GET /api/dashboard``. A tile of a feature
    that is off (Settings > Features) is left out, like its page."""
    text = TEXTS.get(lang, TEXTS['en'])
    hidden = set() if may_see_board else {'incidents', 'open_incidents'}
    hidden |= {t for t, spec in TILES.items() if spec.get('feature') and not feature_on(spec['feature'])}
    return [{'plugin': PLUGIN, 'plugin_name': NAME, 'id': tile, 'label': text[spec['label']], 'size': spec['size'],
             'refresh': spec['refresh'], 'url': f'/api/dashboard/floorbit/{tile}'}
            for tile, spec in TILES.items() if tile not in hidden]


def switches_widget(lang, counts):
    """``counts`` is the status monitor's: online, offline, unknown."""
    text = TEXTS.get(lang, TEXTS['en'])
    total = sum(counts.values())
    return {'type': 'stat', 'value': counts.get('online', 0), 'unit': text['switches_unit'].format(n=total),
            'tone': 'err' if counts.get('offline') else 'ok' if total and counts.get('online') == total else '',
            'sub': text['switches_sub'].format(offline=counts.get('offline', 0), unknown=counts.get('unknown', 0)),
            'link': '/problems', 'min': 0, 'max': total}


def _down_for(text, seconds):
    mins = int(max(0, seconds) // 60)
    if mins < 1:
        return text['just_now']
    if mins < 60:
        return text['mins'].format(n=mins)
    return text['hours'].format(h=mins // 60, m=mins % 60)


def down_widget(lang, statuses, now=None):
    """The switches down right now, longest down first, with how long. ``statuses`` is the status
    monitor's (integrations/monitor.py): id -> name, status and since when."""
    text = TEXTS.get(lang, TEXTS['en'])
    now = time.time() if now is None else now
    if not statuses:
        return {'type': 'status', 'items': [{'label': text['no_status'], 'state': 'unknown'}]}
    down = sorted((s for s in statuses.values() if s.get('status') == 'offline'),
                  key=lambda s: (s.get('since') or now, str(s.get('name') or '')))
    if not down:
        return {'type': 'status', 'items': [{'label': text['all_up'], 'state': 'up'}]}
    items = [{'label': str(s.get('name') or s.get('id')), 'value': _down_for(text, now - (s.get('since') or now)),
              'tone': 'err'} for s in down[:MAX_DOWN]]
    if len(down) > MAX_DOWN:
        items.append({'label': text['more'].format(n=len(down) - MAX_DOWN), 'value': ''})
    return {'type': 'list', 'items': items}


def seats_widget(lang, online, total):
    """``online`` is how many seats are online now, or None when nobody knows."""
    text = TEXTS.get(lang, TEXTS['en'])
    return {'type': 'stat', 'value': '?' if online is None else online, 'unit': text['seats_unit'].format(n=total),
            'tone': '', 'sub': text['unknown'] if online is None else text['seats_sub'], 'link': '/plan',
            'min': 0, 'max': total}


def seats_by_block_widget(lang, blocks, online):
    """Seats online per seat block, as numbers out of the block's seats, so it draws as bars.
    ``blocks`` is block name -> its seat numbers; ``online`` the seats online now, or None."""
    text = TEXTS.get(lang, TEXTS['en'])
    items = []
    for name in sorted(blocks, key=lambda n: (len(n), n)):
        seats = blocks[name]
        if online is None:
            items.append({'label': name, 'value': f'? / {len(seats)}'})
            continue
        n = len(seats & online)
        items.append({'label': name, 'value': f'{n} / {len(seats)}', 'number': n, 'max': len(seats)})
    return {'type': 'list', 'items': items, 'link': '/plan',
            'sub': text['unknown'] if online is None else text['seats_sub']}


def problems_widget(lang, may_see_people):
    from . import problems
    text = TEXTS.get(lang, TEXTS['en'])
    c = problems.current(may_see_people)['counts']
    return {'type': 'stat', 'value': c['down'], 'unit': text['down'],
            'tone': 'err' if c['down'] else 'warn' if c['warn'] else 'ok',
            'sub': text['problems_sub'].format(**c), 'link': '/problems'}


def incidents_widget(lang, now=None):
    from . import incidents
    text = TEXTS.get(lang, TEXTS['en'])
    now = time.time() if now is None else now
    items = incidents.list_all()
    still_open = [i for i in items if i.get('status') == 'open']
    waiting = sum(1 for i in still_open if incidents.is_waiting(i, now))
    worked = sum(1 for i in items if i.get('status') == 'assigned')
    return {'type': 'stat', 'value': len(still_open), 'unit': text['open'],
            'tone': 'warn' if waiting else '' if still_open else 'ok',
            'sub': text['incidents_sub'].format(waiting=waiting, worked=worked), 'link': '/incidents'}


STATE_OF = {'online': 'up', 'offline': 'down'}


def switch_states_widget(lang, statuses, now=None):
    """Every switch with its state, down ones first: the state grid's data."""
    text = TEXTS.get(lang, TEXTS['en'])
    now = time.time() if now is None else now
    order = {'down': 0, 'unknown': 1, 'up': 2}
    items = []
    for s in statuses.values():
        state = STATE_OF.get(s.get('status'), 'unknown')
        detail = text['down_for'].format(t=_down_for(text, now - (s.get('since') or now))) if state == 'down' else ''
        items.append({'label': str(s.get('name') or s.get('id')), 'state': state, 'detail': detail})
    items.sort(key=lambda i: (order[i['state']], i['label']))
    return {'type': 'status', 'items': items[:50], 'link': '/problems'}


def open_incidents_widget(lang, now=None):
    """Open and worked incidents, oldest first: what is left to do."""
    from . import incidents
    text = TEXTS.get(lang, TEXTS['en'])
    now = time.time() if now is None else now
    left = sorted((i for i in incidents.list_all() if i.get('status') in ('open', 'assigned')),
                  key=lambda i: i.get('created_at') or now)

    def where(i):
        if i.get('switch_name'):
            return text['switch_at'].format(name=i['switch_name'])
        if i.get('seat'):
            return text['seat_at'].format(seat=i['seat'])
        return i.get('circuit_name') or ''
    rows = [{'what': i.get('title') or '', 'where': where(i),
             'open': _down_for(text, now - (i.get('created_at') or now))} for i in left]
    return {'type': 'table', 'columns': [{'key': 'what', 'label': text['col_what']},
                                         {'key': 'where', 'label': text['col_where']},
                                         {'key': 'open', 'label': text['col_open']}],
            'rows': rows[:50], 'link': '/incidents'}


def traffic_widget(lang, snapshot):
    """Download and upload over time from the traffic reads (stats.py), in bit/s."""
    text = TEXTS.get(lang, TEXTS['en'])
    samples = (snapshot.get('series') or [])[-500:]
    return {'type': 'series', 'unit': 'bit/s', 'link': '/stats',
            'series': [{'label': text['download'], 'points': [[s['t'], s['down']] for s in samples]},
                       {'label': text['upload'], 'points': [[s['t'], s['up']] for s in samples]}]}


NONE = '\u2013'   # an en dash: no number yet
SI = ('', 'k', 'M', 'G', 'T', 'P')


def _si(value, unit):
    """4.8 Gbit/s, 282 GB: one decimal under ten, as the dashboard writes numbers."""
    value = float(value or 0)
    i = 0
    while abs(value) >= 1000 and i < len(SI) - 1:
        value /= 1000
        i += 1
    digits = 1 if i and abs(value) < 10 else 0
    return f'{value:.{digits}f} {SI[i]}{unit}'


def rate(bps):
    return _si(bps, 'bit/s')


def size(n):
    return _si(n, 'B')


def bandwidth_widget(lang, snapshot):
    """Download and upload together right now, from the latest traffic read (stats.py)."""
    text = TEXTS.get(lang, TEXTS['en'])
    now = snapshot.get('now')
    if not now:
        return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['no_reads'], 'link': '/dashboards/network'}
    return {'type': 'stat', 'value': now['down'] + now['up'], 'unit': 'bit/s', 'link': '/dashboards/network',
            'sub': text['down_up'].format(down=rate(now['down']), up=rate(now['up']))}


def peak_widget(lang, snapshot, now=None):
    """The busiest moment of the event, how long ago, and the last 24 hours' peak next to it."""
    text = TEXTS.get(lang, TEXTS['en'])
    now = time.time() if now is None else now
    peak = snapshot.get('peak')
    if not peak:
        return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['no_reads'], 'link': '/dashboards/network'}
    day = (snapshot.get('day') or {}).get('peak_bps') or 0
    return {'type': 'stat', 'value': peak['bps'], 'unit': 'bit/s', 'link': '/dashboards/network',
            'sub': text['peak_sub'].format(ago=_down_for(text, now - (peak.get('at') or now)), day=rate(day))}


def ports_widget(lang, snapshot):
    """Ports up from the latest read, with how many are down or count errors."""
    text = TEXTS.get(lang, TEXTS['en'])
    now = snapshot.get('now')
    if not now:
        return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['no_reads'], 'link': '/problems'}
    up, down, errors = now.get('ports_up', 0), now.get('ports_down', 0), now.get('ports_errors', 0)
    return {'type': 'stat', 'value': up, 'unit': text['ports_unit'], 'tone': 'warn' if errors else '',
            'sub': text['ports_sub'].format(down=down, errors=errors), 'link': '/problems',
            'min': 0, 'max': up + down}


def uplinks_widget(lang, snapshot):
    """Each uplink's load as a share of its speed, busiest first, so it draws as bars."""
    text = TEXTS.get(lang, TEXTS['en'])
    items = []
    for u in sorted(snapshot.get('uplinks') or [], key=lambda u: -(u.get('utilization') or 0)):
        pct = round((u.get('utilization') or 0) * 100)
        items.append({'label': text['port_at'].format(switch=u.get('switch') or '', port=u.get('port') or '').strip(),
                      'value': f"{pct} % · {rate(u.get('bps'))}", 'number': pct, 'max': 100,
                      'tone': 'err' if pct >= 80 else 'warn' if pct >= 60 else ''})
    return {'type': 'list', 'items': items, 'link': '/dashboards/network'}


def top_ports_widget(lang, snapshot):
    """The busiest seats (or switch ports without a seat) right now. Seat numbers only, no nicks."""
    text = TEXTS.get(lang, TEXTS['en'])
    items = [{'label': text['seat_at'].format(seat=t['seat']) if t.get('seat')
              else text['port_at'].format(switch=t.get('switch') or '', port=t.get('port') or '').strip(),
              'value': rate(t.get('bps')), 'number': t.get('bps') or 0}
             for t in snapshot.get('top') or []]
    return {'type': 'list', 'items': items, 'link': '/dashboards/network'}


CATEGORIES = ('gaming', 'streaming', 'downloads', 'updates', 'web', 'other')


def _no_flows(text):
    return {'type': 'list', 'items': [], 'sub': text['no_flows'], 'link': '/dashboards/traffic'}


def traffic_mix_widget(lang, flows):
    """The last hour's traffic by kind (gaming, streaming, ...), as shares of the whole hall."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not flows:
        return _no_flows(text)
    mix = flows.get('mix_hour') or {}
    total = sum(mix.get(c) or 0 for c in CATEGORIES)
    items = [{'label': text['cat'][c], 'value': f"{round((mix.get(c) or 0) / total * 100)} % · {size(mix.get(c))}",
              'number': mix.get(c) or 0} for c in CATEGORIES if total and mix.get(c)]
    return {'type': 'list', 'items': items, 'sub': text['mix_sub'].format(total=size(total)),
            'link': '/dashboards/traffic'}


def flow_services_widget(lang, flows):
    """The services the hall talks to most, by volume, with how many seats use each."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not flows:
        return _no_flows(text)
    items = [{'label': s.get('name') or '', 'number': s.get('bytes') or 0,
              'value': f"{size(s.get('bytes'))} · {text['seat_count'].format(n=s.get('seats', 0))}"}
             for s in flows.get('services') or []]
    return {'type': 'list', 'items': items, 'link': '/dashboards/traffic'}


def traffic_areas_widget(lang, flows):
    """Volume per area of the hall (aggregates only, issue #25's 5+ seats rule holds there)."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not flows:
        return _no_flows(text)
    items = [{'label': a.get('area') or '', 'value': size(a.get('bytes')), 'number': a.get('bytes') or 0}
             for a in flows.get('areas') or []]
    return {'type': 'list', 'items': items, 'link': '/dashboards/traffic'}


def anomalies_widget(lang, flows, now=None):
    """What the flow collector found odd (P2P, rogue DHCP, ...), newest first. ``flows`` is already
    trimmed for this account: without seats.view an anomaly names no seat."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not flows:
        return {'type': 'status', 'items': [], 'sub': text['no_flows'], 'link': '/dashboards/traffic'}
    now = time.time() if now is None else now
    found = sorted(flows.get('anomalies') or [], key=lambda a: -(a.get('first_seen') or 0))
    if not found:
        return {'type': 'status', 'items': [{'label': text['nothing_odd'], 'state': 'up'}],
                'link': '/dashboards/traffic'}
    bad = ('rogue-dhcp', 'rogue-dns', 'burst')
    return {'type': 'status', 'link': '/dashboards/traffic', 'items': [
        {'label': ' · '.join(x for x in (a.get('title'), a.get('detail')) if x),
         'state': 'down' if a.get('kind') in bad else 'warn',
         'detail': text['for'].format(t=_down_for(text, now - (a.get('first_seen') or now)))} for a in found]}


HEALTH_STATES = ('up', 'down', 'warn', 'unknown')


def service_health_widget(lang, wall):
    """The health wall's checks (DHCP, DNS, firewalls, ...), worst first, with each one's summary.
    ``wall`` is /api/health's, already in the reader's language."""
    text = TEXTS.get(lang, TEXTS['en'])
    checks = wall.get('checks') or []
    if not checks:
        return {'type': 'status', 'items': [], 'sub': text['no_checks'], 'link': '/dashboards/health'}
    order = {'down': 0, 'warn': 1, 'unknown': 2, 'up': 3}
    items = [{'label': c.get('name') or '', 'detail': c.get('summary') or '',
              'state': c.get('status') if c.get('status') in HEALTH_STATES else 'unknown'} for c in checks]
    items.sort(key=lambda i: order[i['state']])
    return {'type': 'status', 'items': items, 'link': '/dashboards/health'}


def internet_uplinks_widget(lang, overview):
    """The event's lines to the internet (services.py uplinks): load as a share of each line's speed."""
    text = TEXTS.get(lang, TEXTS['en'])
    items = []
    for u in overview.get('uplinks') or []:
        name = u.get('name') or ''
        if u.get('status') == 'down':
            items.append({'label': name, 'value': text['link_down'], 'tone': 'err', 'number': 0, 'max': 100})
            continue
        pct = round((u.get('utilization') or 0) * 100)
        items.append({'label': name, 'number': pct, 'max': 100,
                      'value': text['in_out'].format(pct=pct, down=rate(u.get('in_bps')), up=rate(u.get('out_bps'))),
                      'tone': 'err' if pct >= 80 else 'warn' if pct >= 60 or u.get('status') == 'warn' else ''})
    return {'type': 'list', 'items': items, 'link': '/dashboards/services'}


def lancache_widget(lang, cache):
    """How much of the downloads the LAN cache served from its disks (lancache.overview)."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not cache.get('configured'):
        return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['no_cache'], 'link': '/dashboards/services'}
    ratio = cache.get('hit_ratio')
    return {'type': 'stat', 'value': NONE if ratio is None else round(ratio * 100, 1), 'unit': '%',
            'min': 0, 'max': 100, 'link': '/dashboards/services',
            'sub': text['lancache_sub'].format(hit=size(cache.get('hit_bytes')), miss=size(cache.get('miss_bytes')))}


def power_circuits_widget(lang, power):
    """Each circuit's load as a share of its rating, fullest first, in the power page's colours."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not power.get('circuits'):
        return {'type': 'list', 'items': [], 'sub': text['no_circuits'], 'link': '/dashboards/power'}
    warn, crit = power.get('warn') or 80, power.get('crit') or 95
    items = []
    for c in sorted(power['circuits'], key=lambda c: -(c.get('load_pct') or 0)):
        if c.get('tripped') or c.get('state') == 'tripped':
            items.append({'label': c.get('name') or '', 'value': text['tripped'], 'tone': 'err',
                          'number': 0, 'max': 100})
            continue
        pct = c.get('load_pct')
        if pct is None:
            items.append({'label': c.get('name') or '', 'value': NONE})
            continue
        items.append({'label': c.get('name') or '', 'value': f'{round(pct)} %', 'number': round(pct, 1), 'max': 100,
                      'tone': 'err' if pct >= crit else 'warn' if pct >= warn else ''})
    return {'type': 'list', 'items': items, 'link': '/dashboards/power'}


def agents_widget(lang, agents):
    """How many local agents are connected; ``agents`` is agent_link.all_agents() with ``outdated``."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not agents:
        return {'type': 'stat', 'value': 0, 'unit': '', 'sub': text['no_agents'], 'link': '/agents'}
    online = sum(1 for a in agents if a.get('connected'))
    outdated = sum(1 for a in agents if a.get('outdated'))
    return {'type': 'stat', 'value': online, 'unit': text['agents_unit'].format(n=len(agents)),
            'tone': 'err' if online < len(agents) else 'ok', 'min': 0, 'max': len(agents), 'link': '/agents',
            'sub': text['agents_sub'].format(outdated=outdated) if outdated else ''}


DNS_HOURS = 24   # the DNS and games tiles look at the last day, like their pages do by default


def dns_lookups_widget(lang, dns):
    """How many lookups the hall made in the last day, and how many were blocked."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not dns or not dns.get('lookups'):
        return {'type': 'stat', 'value': 0, 'unit': '', 'sub': text['no_dns'], 'link': '/dashboards/traffic'}
    return {'type': 'stat', 'value': dns['lookups'], 'unit': '', 'link': '/dashboards/traffic',
            'sub': text['dns_sub'].format(blocked=dns.get('blocked', 0), hours=DNS_HOURS,
                                          share=round((dns.get('block_share') or 0) * 100, 1))}


def _sites(text, rows, key):
    return [{'label': r.get('site') or '', 'value': text['lookups'].format(n=r.get(key, 0)), 'number': r.get(key, 0)}
            for r in rows]


def dns_sites_widget(lang, dns):
    """The sites the hall looks up most (only those 5+ seats looked up: dns.py's privacy rule)."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not dns:
        return {'type': 'list', 'items': [], 'sub': text['no_dns'], 'link': '/dashboards/traffic'}
    return {'type': 'list', 'items': _sites(text, dns.get('sites') or [], 'lookups'), 'link': '/dashboards/traffic'}


def dns_blocked_widget(lang, dns):
    text = TEXTS.get(lang, TEXTS['en'])
    if not dns:
        return {'type': 'list', 'items': [], 'sub': text['no_dns'], 'link': '/dashboards/traffic'}
    return {'type': 'list', 'items': _sites(text, dns.get('blocked_sites') or [], 'blocked'),
            'link': '/dashboards/traffic'}


def launchers_widget(lang, games):
    """Steam, Epic, Battle.net, ...: how much each pulled, and how much of it the LAN cache served."""
    text = TEXTS.get(lang, TEXTS['en'])
    found = (games or {}).get('launchers') or []
    if not found:
        return {'type': 'list', 'items': [], 'sub': text['no_games'], 'link': '/dashboards/traffic'}
    items = []
    for g in sorted(found, key=lambda g: -((g.get('cache_hit_bytes') or 0) + (g.get('cache_miss_bytes') or 0))):
        total = (g.get('cache_hit_bytes') or 0) + (g.get('cache_miss_bytes') or 0)
        seats = g.get('traffic_seats') or g.get('dns_seats_max') or 0
        # Under 5 seats the pages say nothing about how many (dns.py and flows' privacy rule).
        value = text['launcher_value' if seats else 'launcher_cache'].format(cache=size(g.get('cache_hit_bytes')),
                                                                              seats=seats)
        items.append({'label': g.get('name') or '', 'number': total, 'value': value})
    return {'type': 'list', 'items': items, 'link': '/dashboards/traffic'}


def wifi_clients_widget(lang, wifi):
    """Clients on the Wi-Fi now, by band."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not wifi or not wifi.get('aps'):
        return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['no_wifi'], 'link': '/dashboards/network'}
    bands = wifi.get('bands') or {}
    return {'type': 'stat', 'value': wifi.get('clients') or 0, 'unit': '', 'link': '/dashboards/network',
            'sub': text['wifi_sub'].format(b24=(bands.get('2.4') or {}).get('clients', 0),
                                           b5=(bands.get('5') or {}).get('clients', 0))}


def wifi_aps_widget(lang, wifi):
    """Every access point, down and busy ones first, with its clients."""
    text = TEXTS.get(lang, TEXTS['en'])
    if not wifi or not wifi.get('aps'):
        return {'type': 'status', 'items': [], 'sub': text['no_wifi'], 'link': '/dashboards/network'}
    items = []
    for ap in wifi['aps']:
        state = 'down' if ap.get('status') == 'down' else 'warn' if ap.get('busy') else \
            'up' if ap.get('status') == 'up' else 'unknown'
        detail = text['ap_clients'].format(n=ap.get('clients') or 0)
        items.append({'label': ap.get('name') or '', 'state': state,
                      'detail': f"{detail} · {text['busy']}" if state == 'warn' else detail})
    order = {'down': 0, 'warn': 1, 'unknown': 2, 'up': 3}
    items.sort(key=lambda i: (order[i['state']], i['label']))
    return {'type': 'status', 'items': items, 'link': '/dashboards/network'}
