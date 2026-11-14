"""What the browser needs to know about the server: which integrations are on, display defaults."""
from flask import Blueprint, current_app, jsonify

from .. import sources
from ..runtime import rt

bp = Blueprint('config', __name__)


@bp.route('/api/config')
def get_config():
    registry = current_app.extensions.get('floorbit_plugins')
    feeders = [s.id for s in registry.feeders('inventory')] if registry else []
    return jsonify({
        # The editor's "from NetBox" tab: devices a plugin sent that aren't placed yet.
        'netbox_enabled':    rt.netbox_enabled and 'netbox' in feeders,
        'inventory_sources': feeders,
        # The floor plan's live status, port and heatmap features: any monitoring plugin that is set up.
        'librenms_enabled':  sources.monitoring().enabled(),
        'monitoring_source': sources.monitoring().name,
        'netbox_device_roles': rt.netbox_roles,
        'display_defaults':  rt.display_defaults,
    })
