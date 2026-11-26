"""Traffic categories (issue #1622): the built-in seven plus the tenant's own, for every event.
Rules in floorbit/traffic_categories.py.

- ``GET /api/traffic/categories``: every category with its names and colour, and the colours an own
  one may have.
- ``PUT /api/traffic/categories`` ``{"categories": [{id, name, name_de, colour}]}``: replaces the
  tenant's own ones. Needs settings.manage (auth/roles.py's default for changes).
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, traffic_categories

bp = Blueprint('traffic_categories', __name__)


def _answer():
    return {'categories': traffic_categories.merged(), 'palette': list(traffic_categories.PALETTE),
            'max_own': traffic_categories.MAX_OWN}


@bp.route('/api/traffic/categories', methods=['GET'])
def list_categories():
    return jsonify(_answer())


@bp.route('/api/traffic/categories', methods=['PUT'])
def save_categories():
    body = request.get_json(silent=True)
    try:
        before, after = traffic_categories.save((body or {}).get('categories') if isinstance(body, dict) else None)
    except traffic_categories.CategoryError as exc:
        return jsonify({'error': exc.message}), exc.status
    old, new = {c['id']: c for c in before}, {c['id']: c for c in after}
    for cid in sorted(set(new) - set(old)):
        audit.record('traffic', 'Added a traffic category', g.get('audit_user'), new[cid]['name'])
    for cid in sorted(set(old) - set(new)):
        audit.record('traffic', 'Removed a traffic category', g.get('audit_user'), old[cid]['name'])
    for cid in sorted(set(old) & set(new)):
        if old[cid] != new[cid]:
            audit.record('traffic', 'Changed a traffic category', g.get('audit_user'), new[cid]['name'])
    return jsonify(_answer())
