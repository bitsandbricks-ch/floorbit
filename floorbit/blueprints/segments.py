"""Network segments for on-demand lookups (issue #946). Rules in floorbit/segments.py, docs in
docs/segments.md. Admins only: the routes sit under /api/settings (auth/roles.py).

- ``GET /api/settings/segments``: the segments, and what discovery proposes.
- ``POST /api/settings/segments``: add ``{"vlan", "network", "name"?, "lookups"?}``.
- ``PATCH|DELETE /api/settings/segments/<id>``: change (vlan, network, name, lookups) or remove.
- ``POST /api/settings/segments/discover``: take what discovery found (new ones start with lookups off).
"""
from flask import Blueprint, jsonify, request

from .. import segments

bp = Blueprint('segments', __name__)


def _error(exc):
    return jsonify({'error': str(exc)}), exc.status


@bp.route('/api/settings/segments', methods=['GET'])
def list_segments():
    return jsonify({'segments': segments.all_segments(), 'proposals': segments.proposals()})


@bp.route('/api/settings/segments', methods=['POST'])
def add_segment():
    try:
        return jsonify({'segment': segments.create(request.get_json(silent=True))}), 201
    except segments.SegmentError as exc:
        return _error(exc)


@bp.route('/api/settings/segments/discover', methods=['POST'])
def discover_segments():
    return jsonify(segments.take_proposals())


@bp.route('/api/settings/segments/<seg_id>', methods=['PATCH'])
def change_segment(seg_id):
    try:
        return jsonify({'segment': segments.update(seg_id, request.get_json(silent=True))})
    except segments.SegmentError as exc:
        return _error(exc)


@bp.route('/api/settings/segments/<seg_id>', methods=['DELETE'])
def remove_segment(seg_id):
    try:
        return jsonify(segments.delete(seg_id))
    except segments.SegmentError as exc:
        return _error(exc)
