"""The shared icon library (floorbit/icon_library.py).

- ``GET /api/icons``: the uploaded icons. Everyone who sees the plan.
- ``GET /api/icons/<id>.svg``: one icon, cleaned, served with a locked-down CSP. Cached for good:
  the id is a hash of the file.
- ``POST /api/icons`` ``{"name", "svg"}``: upload one. ``PATCH /api/icons/<id>`` ``{"name"}``,
  ``DELETE /api/icons/<id>``. Admins (``settings.manage``).
"""
from flask import Blueprint, Response, g, jsonify, request

from integrations import events

from .. import audit, icon_library
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('icons', __name__)


@bp.route('/api/icons', methods=['GET'])
def list_icons():
    return jsonify({'icons': icon_library.listing(load_data()), 'max_kb': icon_library.MAX_BYTES // 1024})


@bp.route('/api/icons/<icon_id>.svg', methods=['GET'])
def svg(icon_id):
    icon = icon_library.find(load_data(), icon_id) if icon_library.ID_RE.match(icon_id) else None
    if icon is None:
        return jsonify({'error': 'No such icon'}), 404
    r = Response(icon['svg'], mimetype='image/svg+xml')
    # Even opened on its own, the file can run nothing and load nothing.
    r.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    r.headers['X-Content-Type-Options'] = 'nosniff'
    r.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
    return r


def _change(fn):
    with data_lock:
        data = load_data()
        try:
            result = fn(data)
        except icon_library.IconError as exc:
            return None, (jsonify({'error': str(exc)}), exc.status)
        save_data(data)
    events.publish('inventory.changed', {})
    return result, None


@bp.route('/api/icons', methods=['POST'])
def upload():
    body = request.get_json(silent=True) or {}
    user = g.get('audit_user')
    result, err = _change(lambda data: icon_library.add(data, body.get('name'), body.get('svg'), user))
    if err:
        return err
    icon, new = result
    if new:
        audit.record('icons', 'Uploaded an icon', user=user, target=icon['name'])
    return jsonify(icon_library.public(icon)), 201 if new else 200


@bp.route('/api/icons/<icon_id>', methods=['PATCH'])
def rename(icon_id):
    body = request.get_json(silent=True) or {}
    icon, err = _change(lambda data: icon_library.rename(data, icon_id, body.get('name')))
    if err:
        return err
    audit.record('icons', 'Renamed an icon', user=g.get('audit_user'), target=icon['name'])
    return jsonify(icon_library.public(icon))


@bp.route('/api/icons/<icon_id>', methods=['DELETE'])
def remove(icon_id):
    def go(data):
        name = (icon_library.find(data, icon_id) or {}).get('name', icon_id)
        return name, icon_library.remove(data, icon_id)
    result, err = _change(go)
    if err:
        return err
    name, used = result
    audit.record('icons', 'Removed an icon', user=g.get('audit_user'), target=name)
    return jsonify({'ok': True, 'was_used': used})
