"""Links between switches and the topology (issue #468). Rules in floorbit/links.py, docs in docs/topology.md.

- ``GET /topology``: the page.
- ``GET /api/links``: the switches, every link with its live state, and LLDP neighbours no link explains.
- ``POST /api/links``, ``PUT /api/links/<id>``, ``DELETE /api/links/<id>``: ``floorplan.edit``.
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, links, spa

bp = Blueprint('topology', __name__)


@bp.route('/topology')
def topology_page():
    return spa.render('Topology')


@bp.route('/api/links', methods=['GET'])
def get_links():
    return jsonify(links.topology())


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
