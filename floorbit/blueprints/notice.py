"""Crew notice (issue #246). Rules in floorbit/notice.py.

- ``GET /api/notice``: ``{"notice": {...} | null}``; everyone who sees the floor plan.
- ``PUT /api/notice`` ``{"text", "level", "hours"}``: put one up; ``DELETE /api/notice``: take it down.
  Both need ``incidents.assign`` (leads), see auth/roles.py.
"""
from flask import Blueprint, jsonify, request

from integrations import events

from .. import notice

bp = Blueprint('notice', __name__)


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


@bp.route('/api/notice', methods=['GET'])
def get_notice():
    return jsonify({'notice': notice.current()})


@bp.route('/api/notice', methods=['PUT'])
def put_notice():
    try:
        posted = notice.post(request.get_json(silent=True) or {}, _who())
    except notice.NoticeError as exc:
        return jsonify({'error': str(exc)}), 400
    # The notice goes along so the crew Discord channel can post it (integrations/crew.py).
    events.publish('notice.changed', {'notice': posted})
    return jsonify({'notice': posted})


@bp.route('/api/notice', methods=['DELETE'])
def delete_notice():
    notice.clear()
    events.publish('notice.changed', {'notice': None})
    return jsonify({'notice': None})
