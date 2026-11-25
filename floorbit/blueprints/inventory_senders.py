"""Devices that send but aren't in the inventory (issue #1443, floorbit/unknown_senders.py).

- ``GET /api/inventory/unknown-senders``: each address heard from in the last 24 hours that matches
  no device, with what it sent, when, through which agent and the name it gives. Viewers and up.
- ``POST /api/inventory/unknown-senders/ignore`` ``{"address", "ignored": true|false}``: leave one
  out of the problems, or take it back. Editors and up (``/api/inventory`` WRITE), audit-logged.
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, unknown_senders
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('inventory_senders', __name__)


@bp.route('/api/inventory/unknown-senders', methods=['GET'])
def unknown():
    return jsonify({'senders': unknown_senders.collect(load_data())})


@bp.route('/api/inventory/unknown-senders/ignore', methods=['POST'])
def ignore():
    body = request.get_json(silent=True) or {}
    address = body.get('address')
    if not isinstance(address, str) or not address.strip():
        return jsonify({'error': 'Send the address'}), 400
    on = body.get('ignored', True) is not False
    with data_lock:
        data = load_data()
        unknown_senders.set_ignored(data, address.strip(), on)
        save_data(data)
    audit.record('inventory', 'Ignored an unknown sender' if on else 'Stopped ignoring an unknown sender',
                 user=g.get('audit_user'), target=address.strip()[:80])
    return jsonify({'ignored': unknown_senders.ignored(data)})
