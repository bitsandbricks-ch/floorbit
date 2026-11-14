"""Outgoing webhooks (issue #40). Rules in floorbit/webhooks.py, docs in docs/api.md#webhooks.

- ``GET /settings/webhooks``: the page (React), admins only.
- ``GET|POST /api/settings/webhooks``: list, add ``{"name", "url", "events": [...]}`` (the answer holds
  the signing secret, once).
- ``PATCH|DELETE /api/settings/webhooks/<id>``: change (name, url, events, active) or remove.
- ``POST /api/settings/webhooks/<id>/test``: send a ping now. ``.../secret``: a new secret, shown once.
"""
from flask import Blueprint, g, jsonify, request

from .. import spa
from .. import webhooks as hooks

bp = Blueprint('webhooks', __name__)


def _error(exc):
    return jsonify({'error': str(exc)}), exc.status


@bp.route('/settings/webhooks')
def webhooks_page():
    return spa.render('Webhooks')


@bp.route('/api/settings/webhooks', methods=['GET'])
def list_hooks():
    return jsonify({'webhooks': hooks.all_hooks(), 'events': list(hooks.EVENTS)})


@bp.route('/api/settings/webhooks', methods=['POST'])
def add_hook():
    try:
        hook, secret = hooks.create(request.get_json(silent=True), user=g.get('audit_user'))
    except hooks.WebhookError as exc:
        return _error(exc)
    return jsonify({'webhook': hook, 'secret': secret}), 201


@bp.route('/api/settings/webhooks/<hook_id>', methods=['PATCH'])
def change_hook(hook_id):
    try:
        return jsonify(hooks.update(hook_id, request.get_json(silent=True)))
    except hooks.WebhookError as exc:
        return _error(exc)


@bp.route('/api/settings/webhooks/<hook_id>', methods=['DELETE'])
def remove_hook(hook_id):
    try:
        return jsonify(hooks.delete(hook_id))
    except hooks.WebhookError as exc:
        return _error(exc)


@bp.route('/api/settings/webhooks/<hook_id>/test', methods=['POST'])
def test_hook(hook_id):
    try:
        return jsonify(hooks.test(hook_id))
    except hooks.WebhookError as exc:
        return _error(exc)


@bp.route('/api/settings/webhooks/<hook_id>/secret', methods=['POST'])
def rotate_secret(hook_id):
    try:
        hook, secret = hooks.new_secret(hook_id)
    except hooks.WebhookError as exc:
        return _error(exc)
    return jsonify({'webhook': hook, 'secret': secret})
