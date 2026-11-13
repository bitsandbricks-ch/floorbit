"""What the browser needs to know about the server: which integrations are on, display defaults."""
from flask import Blueprint, jsonify

from ..runtime import rt

bp = Blueprint('config', __name__)


@bp.route('/api/config')
def get_config():
    return jsonify({
        'netbox_enabled':    rt.netbox_enabled,
        'librenms_enabled':  rt.librenms_enabled,
        'netbox_device_roles': rt.netbox_roles,
        'display_defaults':  rt.display_defaults,
    })
