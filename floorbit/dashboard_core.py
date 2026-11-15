"""Floorbit's own dashboard tiles (issue #302): problems and incidents, with no plugin installed.

They come as ordinary widget tiles from the plugin id ``floorbit`` (which no plugin may take), so
layouts, the wall view and the widget renderer treat them like any plugin's. Texts follow the
browser's language, like the other pages the server writes text for.
"""
import time
from urllib.parse import quote

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
           'gear': 'Gear out', 'gear_unit': 'of {n}', 'gear_sub': 'Most with {top}', 'gear_none': 'Everything is here'},
    'de': {'problems': 'Probleme jetzt', 'incidents': 'Störungen', 'down': 'ausgefallen', 'open': 'offen',
           'switches': 'Switches', 'switches_unit': 'von {n} online',
           'switches_sub': '{offline} offline · {unknown} unbekannt',
           'seats': 'Plätze online', 'seats_unit': 'von {n}', 'seats_sub': 'Aus der letzten Port-Abfrage',
           'unknown': 'Gerade nicht bekannt: keine aktuelle Port-Abfrage',
           'problems_sub': '{warn} zum Anschauen · {attention} Port-Probleme · {muted} stumm',
           'incidents_sub': '{waiting} warten seit 10+ Min. · {worked} in Arbeit',
           'gear': 'Material draussen', 'gear_unit': 'von {n}', 'gear_sub': 'Am meisten bei {top}',
           'gear_none': 'Alles ist da'},
}
TILES = ('problems', 'incidents', 'switches', 'seats', 'gear')   # #304 added switches and seats, #326 gear


def tiles(lang, may_see_board, may_see_gear=False):
    """The tile list entries, next to the plugins' in ``GET /api/dashboard``."""
    text = TEXTS.get(lang, TEXTS['en'])
    hidden = {t for t, ok in (('incidents', may_see_board), ('gear', may_see_gear)) if not ok}
    return [{'plugin': PLUGIN, 'plugin_name': NAME, 'id': tile, 'label': text[tile], 'size': 'small',
             'refresh': 30, 'url': f'/api/dashboard/floorbit/{tile}'}
            for tile in TILES if tile not in hidden]


def gear_widget(lang, data=None):
    """How many pieces are out and who has the most (issue #326). Names a holder, so crew only."""
    from . import gear
    text = TEXTS.get(lang, TEXTS['en'])
    rows = gear.items(data)
    held = {}
    for r in rows:
        if r['loan']:
            held[r['loan']['to']] = held.get(r['loan']['to'], 0) + 1
    out = sum(held.values())
    top = min(held.items(), key=lambda kv: (-kv[1], kv[0].lower())) if held else None
    return {'type': 'stat', 'value': out, 'unit': text['gear_unit'].format(n=len(rows)),
            'tone': 'warn' if out else 'ok',
            'sub': text['gear_sub'].format(top=f'{top[0]} ({top[1]})') if top else text['gear_none'],
            'link': f'/gear?holder={quote(top[0])}' if top else '/gear'}


def switches_widget(lang, counts):
    """``counts`` is the status monitor's: online, offline, unknown."""
    text = TEXTS.get(lang, TEXTS['en'])
    total = sum(counts.values())
    return {'type': 'stat', 'value': counts.get('online', 0), 'unit': text['switches_unit'].format(n=total),
            'tone': 'err' if counts.get('offline') else 'ok' if total and counts.get('online') == total else '',
            'sub': text['switches_sub'].format(offline=counts.get('offline', 0), unknown=counts.get('unknown', 0)),
            'link': '/problems'}


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
