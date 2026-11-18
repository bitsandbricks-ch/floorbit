"""Links between switches and the topology (issue #468). Rules in floorbit/links.py, docs in docs/topology.md.

- ``GET /topology``: the page.
- ``GET /api/links``: the switches, every link with its live state, and LLDP neighbours no link explains.
- ``POST /api/links``, ``PUT /api/links/<id>``, ``DELETE /api/links/<id>``: ``floorplan.edit``.
- ``GET /api/links/ports?switch=<name>``: that switch's ports and which link uses each, for the port picker
  (``floorplan.edit``).
- ``PUT /api/links/layout`` ``{positions, replace}``, ``DELETE /api/links/layout``: where the boxes sit on
  the diagram, shared by everyone (``floorplan.edit``).
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, links, spa

bp = Blueprint('topology', __name__)
LAYOUT_ERROR = 'The places could not be saved.'


@bp.route('/topology')
def topology_page():
    return spa.render('Topology')


@bp.route('/api/links', methods=['GET'])
def get_links():
    return jsonify(links.topology())


@bp.route('/api/links/layout', methods=['PUT'])
def save_layout():
    try:
        places = links.save_layout(request.get_json(silent=True) or {})
    except links.LinkError as exc:
        # A fixed text: the page only ever sends places it drew, so the detail helps nobody.
        return jsonify({'error': LAYOUT_ERROR}), exc.status
    return jsonify({'layout': places})


@bp.route('/api/links/ports', methods=['GET'])
def switch_ports():
    """``?switch=<name>``: the switch's ports for the link form's port picker (``floorplan.edit``)."""
    return jsonify({'ports': links.ports_of(request.args.get('switch', ''))})


@bp.route('/api/links/layout', methods=['DELETE'])
def reset_layout():
    links.reset_layout()
    audit.record('floor plan', 'Arranged the topology again', g.get('audit_user'), '')
    return jsonify({'ok': True})


@bp.route('/api/links', methods=['POST'])
@bp.route('/api/links/<link_id>', methods=['PUT'])
def save_link(link_id=None):
    try:
        link = links.save(request.get_json(silent=True) or {}, g.get('audit_user'), link_id)
    except links.LinkError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('floor plan', 'Changed link' if link_id else 'Added link', g.get('audit_user'),
                 f"{link['a']} {link['a_port']} to {link['b']} {link['b_port']}")
    return jsonify(link), 200 if link_id else 201


@bp.route('/api/links/<link_id>', methods=['DELETE'])
def delete_link(link_id):
    gone = links.delete(link_id)
    if gone is None:
        return jsonify({'error': 'No such link.'}), 404
    audit.record('floor plan', 'Removed link', g.get('audit_user'),
                 f"{gone['a']} {gone['a_port']} to {gone['b']} {gone['b_port']}")
    return jsonify({'ok': True})
