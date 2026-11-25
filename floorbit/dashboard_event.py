"""The Event in numbers as tiles (#1045): what the old stats wall view showed, one number each, so a
public dashboard is built from tiles like every other. The numbers come from ``stats_wall.facts`` and
are already public (``/wall.json``): hall-wide and per seat block only, no nicks, IPs or switch names.
"""
import time

# dashboard_core lists these tiles, so its helpers are imported where they are used.

TEXTS = {
    'en': {'event_downloaded': 'Downloaded', 'event_peak': 'Busiest moment', 'event_online_max': 'Most seats online',
           'event_busiest_hour': 'Busiest hour', 'event_loyal_block': 'Most loyal block',
           'event_cache_saved': 'From the LAN cache', 'event_games': 'Top games',
           'event_downloads': 'Most downloaded', 'event_sites': 'Top sites in the hall',
           'wall_seats': '{n} seats', 'wall_disks': '{n} % came from the LAN cache\'s disks',
           'wall_via': {'dns': 'DNS', 'traffic': 'Traffic', 'servers': 'Game servers'},
           'wall_cats': {'gaming': 'gaming', 'streaming': 'streaming', 'social': 'social', 'downloads': 'downloads',
                    'updates': 'updates', 'web': 'web', 'other': 'other'},
           'wall_no_downloads': 'Nothing from the LAN cache yet', 'wall_no_sites': 'No sites seen yet',
           'running': 'in {n} h', 'at': 'at {time}', 'of': 'of {n} seats', 'avg': 'average {rate}',
           'loyal': '{name} · online {hours} h on average', 'cache': 'not downloaded twice from the internet',
           'nothing': 'Nothing counted yet', 'no_games': 'No games seen yet',
           'off': 'The stats wall is switched off'},
    'de': {'event_downloaded': 'Heruntergeladen', 'event_peak': 'Spitzenmoment',
           'event_online_max': 'Meiste Plätze online',
           'event_busiest_hour': 'Stärkste Stunde', 'event_loyal_block': 'Treuester Block',
           'event_cache_saved': 'Aus dem LAN-Cache', 'event_games': 'Top-Spiele',
           'event_downloads': 'Meistgeladen', 'event_sites': 'Top-Seiten in der Halle',
           'wall_seats': '{n} Plätze', 'wall_disks': '{n} % kamen von den Platten des LAN-Cache',
           'wall_via': {'dns': 'DNS', 'traffic': 'Traffic', 'servers': 'Gameserver'},
           'wall_cats': {'gaming': 'Gaming', 'streaming': 'Streaming', 'social': 'Social', 'downloads': 'Downloads',
                    'updates': 'Updates', 'web': 'Web', 'other': 'Anderes'},
           'wall_no_downloads': 'Noch nichts aus dem LAN-Cache', 'wall_no_sites': 'Noch keine Seiten gesehen',
           'running': 'in {n} Std.', 'at': 'um {time}', 'of': 'von {n} Plätzen', 'avg': 'im Schnitt {rate}',
           'loyal': '{name} · im Schnitt {hours} Std. online', 'cache': 'nicht doppelt aus dem Internet geladen',
           'nothing': 'Noch nichts gezählt', 'no_games': 'Noch keine Spiele gesehen',
           'off': 'Die Statistikwand ist ausgeschaltet'},
}

# Public: anyone may see them on a public dashboard (dashboards.PUBLIC_TILES), like the stats wall.
TILES = {tid: {'label': tid, 'size': 'small', 'refresh': 60, 'feature': 'stats_wall'}
         for tid in ('event_downloaded', 'event_peak', 'event_online_max', 'event_busiest_hour',
                     'event_loyal_block', 'event_cache_saved', 'event_games', 'event_downloads', 'event_sites')}
LISTS = ('event_games', 'event_downloads', 'event_sites')


def _clock(t):
    return time.strftime('%H:%M', time.localtime(t))


def _none(text):
    from .dashboard_core import NONE
    return {'type': 'stat', 'value': NONE, 'unit': '', 'sub': text['nothing']}


def off(tile, lang):
    """What a tile shows while the stats wall is switched off."""
    from .dashboard_core import NONE
    sub = TEXTS.get(lang, TEXTS['en'])['off']
    return {'type': 'list', 'items': [], 'sub': sub} if tile in LISTS else \
        {'type': 'stat', 'value': NONE, 'unit': '', 'sub': sub}


def widget(tile, lang, f):
    """Tile ``tile`` from the wall's facts ``f``."""
    from .dashboard_core import rate
    from .stats_wall import size
    text = TEXTS.get(lang, TEXTS['en'])
    if tile == 'event_downloaded':
        if not f.get('downloaded'):
            return _none(text)
        hours = f.get('running_hours')
        return {'type': 'stat', 'value': f['downloaded'], 'unit': 'B',
                # A clock left running since a past event would read "in 500000 h".
                **({'sub': text['running'].format(n=round(hours))} if hours and 0 < hours <= 24 * 30 else {})}
    if tile == 'event_peak':
        peak = f.get('peak') or {}
        if not peak.get('bps'):
            return _none(text)
        return {'type': 'stat', 'value': peak['bps'], 'unit': 'bit/s',
                **({'sub': text['at'].format(time=_clock(peak['at']))} if peak.get('at') else {})}
    if tile == 'event_online_max':
        if not f.get('online_max'):
            return _none(text)
        return {'type': 'stat', 'value': f['online_max'], 'unit': '', 'sub': text['of'].format(n=f.get('seats') or 0),
                'min': 0, 'max': f.get('seats') or f['online_max']}
    if tile == 'event_busiest_hour':
        hour = f.get('busiest_hour') or {}
        if not hour.get('t'):
            return _none(text)
        return {'type': 'stat', 'value': _clock(hour['t']), 'text': _clock(hour['t']), 'unit': '',
                'sub': text['avg'].format(rate=rate(hour.get('bps') or 0))}
    if tile == 'event_loyal_block':
        block = f.get('loyal_block') or {}
        if not block.get('name'):
            return _none(text)
        return {'type': 'stat', 'value': round((block.get('share') or 0) * 100), 'unit': '%', 'min': 0, 'max': 100,
                'sub': text['loyal'].format(name=block['name'], hours=block.get('hours') or 0)}
    if tile == 'event_cache_saved':
        if not f.get('cache_saved'):
            return _none(text)
        return {'type': 'stat', 'value': f['cache_saved'], 'unit': 'B', 'sub': text['cache']}
    if tile == 'event_games':
        games = f.get('games') or []
        if not games:
            return {'type': 'list', 'items': [], 'sub': text['no_games']}
        return {'type': 'list', 'items': [
            {'label': g['name'], 'value': text['wall_seats'].format(n=g.get('seats') or 0), 'tone': '',
             'number': g['bar'], 'max': 1,
             **({'sub': ' + '.join(text['wall_via'][v] for v in g['via'])} if g.get('via') else {})}
            for g in games]}
    if tile == 'event_downloads':
        rows = f.get('downloads') or []
        if not rows:
            return {'type': 'list', 'items': [], 'sub': text['wall_no_downloads']}
        share = f.get('cache_hit_share')
        return {'type': 'list', 'items': [{'label': r['name'], 'value': size(r['bytes'], lang), 'tone': '',
                                           'number': r['bar'], 'max': 1} for r in rows],
                **({'sub': text['wall_disks'].format(n=round(share * 100))} if share is not None else {})}
    if tile == 'event_sites':
        rows = f.get('sites') or []
        if not rows:
            return {'type': 'list', 'items': [], 'sub': text['wall_no_sites']}
        return {'type': 'list', 'items': [
            {'label': r['name'], 'value': text['wall_seats'].format(n=r['seats']), 'tone': '',
             'number': r['bar'], 'max': 1,
             **({'sub': text['wall_cats'].get(r['category'], r['category'])} if r.get('category') else {})}
            for r in rows]}
    raise KeyError(tile)

