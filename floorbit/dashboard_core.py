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
           'seat_at': 'Seat {seat}', 'traffic': 'Traffic', 'download': 'Download', 'upload': 'Upload'},
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
           'seat_at': 'Platz {seat}', 'traffic': 'Verkehr', 'download': 'Download', 'upload': 'Upload'},
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
}
MAX_DOWN = 20   # a big screen reads a short list; the rest is "+ n more"


def tiles(lang, may_see_board):
    """The tile list entries, next to the plugins' in ``GET /api/dashboard``."""
    text = TEXTS.get(lang, TEXTS['en'])
    hidden = set() if may_see_board else {'incidents', 'open_incidents'}
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
            'link': '/problems'}


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
            'tone': '', 'sub': text['unknown'] if online is None else text['seats_sub'], 'link': '/plan'}


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
