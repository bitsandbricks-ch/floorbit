"""The LAN cache view and widgets (docs/lancache.md):

- ``GET /api/lancache?hours=24``: what the cache served per service and hour, the downloads enough
  players fetched, suspect files, lancache-dns lookups, and each agent's view of the cache machine.
  Hall-wide numbers only. Clearing the cache is the plugin's action (``/api/plugins/lancache/...``).
"""
from flask import Blueprint, current_app, jsonify, request

from .. import agent_plugins
from ..lancache import overview, settings

bp = Blueprint('lancache', __name__)


def _plugin():
    """(installed, on): the plugin comes from the Marketplace, so it may not be there at all."""
    registry = current_app.extensions.get('floorbit_plugins')
    spec = registry.specs.get('lancache') if registry else None
    return spec is not None, bool(spec and registry.enabled(spec))


def _has_data():
    """True once Floorbit reads a cache log itself or an agent reports one, with or without the plugin."""
    stats = current_app.extensions.get('floorbit_lancache')
    return bool(stats is not None and (stats.demo or stats.hours or stats.remote or settings()['log']))


@bp.route('/api/lancache', methods=['GET'])
def data():
    try:
        hours = min(max(int(request.args.get('hours') or 24), 1), 168)
    except ValueError:
        hours = 24
    stats = current_app.extensions.get('floorbit_lancache')
    out = overview(stats, agent_plugins.health_of('lancache'), hours=hours)
    out['plugin_installed'], out['plugin_on'] = _plugin()
    return jsonify(out)
