"""Public stats wall (issue #105). The facts come from floorbit/stats_wall.py; see docs/stats-wall.md.

- ``GET /wall``: the page, for a big screen or attendees' phones, no account. Off unless Settings >
  Attendee pages turns it on. ``?screen=1`` for the big screen: larger type, no scrolling.
- ``GET /wall.json``: the same numbers as JSON, for the event website or a Discord bot.

Hall-wide and per seat block only: no nicks, IPs, MACs, seat numbers or switch names.
"""
import time

from flask import Blueprint, current_app, jsonify

from .. import features, games, incidents, spa, stats_wall
from ..store import load_data
from .flows import current as current_flows

bp = Blueprint('stats_wall', __name__)


def online_seats(now=None):
    """The online seats from the latest port read, or None when there is no recent read;
    and when that read was."""
    from ..attention import AttentionWatch
    seats = current_app.extensions['floorbit_stats'].seats()
    last = seats.get('last_poll')
    now = time.time() if now is None else now
    # Three missed reads and the count would lie; better to say we don't know.
    if not last or now - last > 3 * AttentionWatch.interval():
        return None, last
    return set(seats.get('seats') or {}), last


def page_on():
    return bool(current_app.extensions['floorbit_settings'].get('public.stats_wall'))


def _facts(now=None):
    now = time.time() if now is None else now
    ext = current_app.extensions
    event = ext['floorbit_stats'].event()
    online, _last = online_seats(now)
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


@bp.route('/wall')
def wall_page():
    """The page is React (frontend/src/pages/public/PublicWall.tsx), reading /wall.json; 404 while
    it is switched off."""
    html, status = spa.render('The event in numbers')
    return html, status if page_on() else 404


@bp.route('/wall.json')
def wall_json():
    if not page_on():
        return jsonify({'error': 'The stats wall is switched off.'}), 404
    return jsonify(_facts())


for _view in (wall_page, wall_json):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account
