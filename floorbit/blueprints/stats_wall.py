"""Public stats wall (issue #105). The facts come from floorbit/stats_wall.py; see docs/stats-wall.md.

- ``GET /wall``: the page, for a big screen or attendees' phones, no account. Off unless Settings >
  Attendee pages turns it on. ``?screen=1`` for the big screen: larger type, no scrolling.
- ``GET /wall.json``: the same numbers as JSON, for the event website or a Discord bot.

Hall-wide and per seat block only: no nicks, IPs, MACs, seat numbers or switch names.
"""
import time

from flask import Blueprint, current_app, jsonify, render_template, request
from markupsafe import Markup

from .. import features, games, incidents, stats_wall
from ..store import load_data
from .attendee import _online
from .flows import current as current_flows
from .status_page import _stamp

bp = Blueprint('stats_wall', __name__)

TEXTS = {
    'en': {'title': 'The event in numbers', 'off': 'This page is switched off.',
           'online': 'Seats online now', 'of': 'of {n}', 'unknown': 'not known right now',
           'online_max': 'Most seats online at once', 'downloaded': 'Downloaded so far',
           'peak': 'Bandwidth peak', 'at': 'at {time}', 'busiest': 'Busiest hour', 'avg': '{rate} on average',
           'loyal': 'Most loyal seat block', 'loyal_detail': 'Block {name}: each seat online {hours} h on average',
           'games': 'What the hall plays', 'cache': 'Served from the LAN cache',
           'cache_detail': 'downloaded once, not again from the internet',
           'running': 'Running for', 'hours': '{n} h',
           'nothing': 'Nothing to show yet. Check back once the event is running.',
           'privacy': 'Counts for the whole hall and per seat block only: no names, seats or addresses.',
           'updated': 'Updated {time}. This page reloads every minute.'},
    'de': {'title': 'Der Event in Zahlen', 'off': 'Diese Seite ist ausgeschaltet.',
           'online': 'Plätze jetzt online', 'of': 'von {n}', 'unknown': 'gerade nicht bekannt',
           'online_max': 'Am meisten Plätze gleichzeitig online', 'downloaded': 'Bisher heruntergeladen',
           'peak': 'Bandbreiten-Spitze', 'at': 'um {time}', 'busiest': 'Stärkste Stunde', 'avg': '{rate} im Schnitt',
           'loyal': 'Treuester Platzblock', 'loyal_detail': 'Block {name}: jeder Platz im Schnitt {hours} h online',
           'games': 'Was die Halle spielt', 'cache': 'Aus dem LAN-Cache geliefert',
           'cache_detail': 'einmal heruntergeladen, nicht nochmals aus dem Internet',
           'running': 'Läuft seit', 'hours': '{n} h',
           'nothing': 'Noch nichts zu zeigen. Schau wieder rein, sobald der Event läuft.',
           'privacy': 'Zahlen für die ganze Halle und pro Platzblock: keine Namen, Plätze oder Adressen.',
           'updated': 'Stand {time}. Die Seite lädt jede Minute neu.'},
}


def page_on():
    return bool(current_app.extensions['floorbit_settings'].get('public.stats_wall'))


def _facts(now=None):
    now = time.time() if now is None else now
    ext = current_app.extensions
    event = ext['floorbit_stats'].event()
    online, _last = _online(now)
    data = load_data()
    seats = incidents.seat_numbers(data)
    start = event.get('start')
    hours = max(1, min(168, int((now - start) // 3600) + 1)) if start else 24
    try:
        dns_stats = ext.get('floorbit_dns') if features.on('dns') else None
        flows = current_flows() if features.on('traffic') else None
        insights = games.insights(dns_stats, flows, ext.get('floorbit_lancache'), hours, now)
    except Exception as exc:  # noqa: BLE001  # a broken source must not take the wall down
        print(f'[wall] no game numbers: {exc}')
        insights = None
    return stats_wall.facts(event, None if online is None else len(online & set(seats)), len(seats), insights, now=now)


def _big(text):
    """'1.5 TB' as the number with a smaller unit after it."""
    number, _, unit = str(text).partition(' ')
    return Markup('{}<small>{}</small>').format(number, unit) if unit else text


@bp.route('/wall')
def wall_page():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    text = TEXTS[lang]
    if not page_on():
        return render_template('wall.html', lang=lang, t=text, off=True), 404
    now = time.time()
    return render_template('wall.html', lang=lang, t=text, off=False, f=_facts(now), now=now, stamp=_stamp,
                           size=lambda v: stats_wall.size(v, lang), rate=lambda v: stats_wall.rate(v, lang), big=_big,
                           num=lambda v: str(v).replace('.', ',') if lang == 'de' else str(v),
                           screen=request.args.get('screen') == '1')


@bp.route('/wall.json')
def wall_json():
    if not page_on():
        return jsonify({'error': 'The stats wall is switched off.'}), 404
    return jsonify(_facts())


for _view in (wall_page, wall_json):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account
