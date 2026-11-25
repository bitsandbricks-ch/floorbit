"""Game and launcher insights (issue #88). The numbers come from floorbit/games.py.

- ``GET /api/games?hours=24``: per launcher, game (``titles``) and site group the DNS lookups, traffic,
  what the LAN cache served and the players on the event's game servers, the gaming services the event
  named, the other caches, and the cache's hit ratio per hour, for the last 1 to 168 hours. Hall-wide only.
"""
from flask import Blueprint, current_app, jsonify, request

from .. import features, game_servers, games, spa
from .flows import current as current_flows

bp = Blueprint('games', __name__)


@bp.route('/games')
def games_page():
    return spa.render('Games')


@bp.route('/api/games', methods=['GET'])
def get_games():
    try:
        hours = int(request.args.get('hours', 24))
    except ValueError:
        hours = 0
    if not 1 <= hours <= 168:
        return jsonify({'error': 'hours is a whole number from 1 to 168.'}), 400
    ext = current_app.extensions
    dns_stats = ext.get('floorbit_dns') if features.on('dns') else None
    flows = current_flows() if features.on('traffic') else None
    return jsonify(games.insights(dns_stats, flows, ext.get('floorbit_lancache'), hours, servers=servers_now()))


def servers_now():
    """The game servers with their last answer, without asking them now."""
    return [{**s, **game_servers.poller.state(s['id'])} for s in game_servers.listing()]
