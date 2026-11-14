"""What the browser needs to know about the server: which integrations are on, display defaults."""
from flask import Blueprint, current_app, jsonify

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
        'librenms_enabled':  rt.librenms_enabled,
        'netbox_device_roles': rt.netbox_roles,
        'display_defaults':  rt.display_defaults,
    })
