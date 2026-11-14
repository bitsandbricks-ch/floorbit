"""Game and launcher insights (issue #88). The numbers come from floorbit/games.py.

- ``GET /games``: the page.
- ``GET /api/games?hours=24``: per launcher the DNS lookups, traffic and what the LAN cache served,
  the gaming services the event named, the other caches, and the cache's hit ratio per hour, for the
  last 1 to 168 hours. Hall-wide only.
"""
from flask import Blueprint, current_app, jsonify, request

from .. import features, games, spa
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
    return jsonify(games.insights(dns_stats, flows, ext.get('floorbit_lancache'), hours))
