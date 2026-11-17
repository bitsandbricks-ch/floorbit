"""The LAN cache page (docs/lancache.md):

- ``GET /lancache``: the page (React).
- ``GET /api/lancache?hours=24``: what the cache served per service and hour, the downloads enough
  players fetched, suspect files, lancache-dns lookups, and each agent's view of the cache machine.
  Hall-wide numbers only. Clearing the cache is the plugin's action (``/api/plugins/lancache/...``).
"""
from flask import Blueprint, current_app, jsonify, request

from .. import agent_plugins, spa
from ..builtin_plugins.lancache.plugin import overview

bp = Blueprint('lancache', __name__)


def _plugin_on():
    registry = current_app.extensions.get('floorbit_plugins')
    spec = registry.specs.get('lancache') if registry else None
    return bool(spec and registry.enabled(spec))


@bp.app_context_processor
def lancache_flags():
    try:
        return {'lancache_on': _plugin_on()}
    except Exception:  # noqa: BLE001 - a nav link must never break a page
        return {'lancache_on': False}


@bp.route('/lancache')
def page():
    return spa.render('LAN cache')


@bp.route('/api/lancache', methods=['GET'])
def data():
    try:
        hours = min(max(int(request.args.get('hours') or 24), 1), 168)
    except ValueError:
        hours = 24
    stats = current_app.extensions.get('floorbit_lancache')
    out = overview(stats, agent_plugins.health_of('lancache'), hours=hours)
    out['plugin_on'] = _plugin_on()
    return jsonify(out)
