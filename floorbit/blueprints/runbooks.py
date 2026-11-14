"""Runbooks (issue #102). The rules live in floorbit/runbooks.py.

- ``GET /runbooks``: the page (React); ``/runbooks?open=<id>`` opens one (what the incident links to).
- ``GET /api/runbooks``: the runbooks and the kinds of incident.
- ``POST /api/runbooks``, ``PATCH /api/runbooks/<id>``, ``DELETE /api/runbooks/<id>``.
- ``POST /api/runbooks/<id>/move`` with ``{"step": -1}``: the first runbook for a kind is the one used.

Reading needs ``incidents.work``, changing ``incidents.assign`` (leads and admins, auth/roles.py).
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, runbooks, spa

bp = Blueprint('runbooks', __name__)


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _done(action, target):
    audit.record('runbooks', action, g.get('audit_user'), target)
    events.publish('runbooks.changed', {})


def _error(exc):
    return jsonify({'error': str(exc)}), exc.status


@bp.route('/runbooks')
def runbooks_page():
    return spa.render('Runbooks')


@bp.route('/api/runbooks', methods=['GET'])
def list_runbooks():
    return jsonify({'runbooks': runbooks.all_runbooks(), 'kinds': list(runbooks.KINDS)})


@bp.route('/api/runbooks', methods=['POST'])
def add_runbook():
    try:
        book = runbooks.add(request.get_json(silent=True) or {}, _who())
    except runbooks.RunbookError as exc:
        return _error(exc)
    _done('Added runbook', book['title'])
    return jsonify(book), 201


@bp.route('/api/runbooks/<book_id>', methods=['PATCH'])
def update_runbook(book_id):
    try:
        book = runbooks.update(book_id, request.get_json(silent=True) or {}, _who())
    except runbooks.RunbookError as exc:
        return _error(exc)
    _done('Changed runbook', book['title'])
    return jsonify(book)


@bp.route('/api/runbooks/<book_id>', methods=['DELETE'])
def delete_runbook(book_id):
    try:
        runbooks.delete(book_id)
    except runbooks.RunbookError as exc:
        return _error(exc)
    _done('Removed runbook', book_id)
    return jsonify({'ok': True})


@bp.route('/api/runbooks/<book_id>/move', methods=['POST'])
def move_runbook(book_id):
    try:
        runbooks.move(book_id, int((request.get_json(silent=True) or {}).get('step') or 1))
    except runbooks.RunbookError as exc:
        return _error(exc)
    except (TypeError, ValueError):
        return jsonify({'error': 'step is -1 or 1.'}), 400
    _done('Moved runbook', book_id)
    return jsonify({'ok': True})
