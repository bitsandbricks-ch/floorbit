"""API tokens and the API's version (issue #40). Rules in auth/tokens.py, docs in docs/api.md.

- ``GET /api/version``: ``{"api": 1, "app": "<version>"}``. Every ``/api/`` answer also carries
  ``Floorbit-API: 1``; the number goes up only when an existing answer changes in a way that breaks a
  client (a field removed or renamed). New fields and new endpoints don't change it.
- ``GET /settings/api``: the page (React), admins only.
- ``GET|POST /api/settings/api-tokens``, ``DELETE /api/settings/api-tokens/<id>``: list, make
  ``{"name", "role", "read_only", "expires_days"}`` (the answer holds the token, once) and revoke.
"""
from flask import Blueprint, current_app, g, jsonify, request

from auth import tokens

from .. import spa

API_VERSION = 1
bp = Blueprint('api_tokens', __name__)


@bp.after_app_request
def version_header(response):
    if request.path.startswith('/api/'):
        response.headers['Floorbit-API'] = str(API_VERSION)
    return response


@bp.route('/api/version', methods=['GET'])
def version():
    return jsonify({'api': API_VERSION, 'app': current_app.config.get('FLOORBIT_VERSION') or '0'})


@bp.route('/settings/api')
def tokens_page():
    return spa.render('ApiTokens')


@bp.route('/api/settings/api-tokens', methods=['GET'])
def list_tokens():
    return jsonify({'tokens': tokens.all_tokens(), 'max_days': tokens.MAX_DAYS})


@bp.route('/api/settings/api-tokens', methods=['POST'])
def create_token():
    body = request.get_json(silent=True) or {}
    try:
        made, secret = tokens.create(body.get('name'), body.get('role'), read_only=bool(body.get('read_only')),
                                     expires_days=body.get('expires_days'), user=g.get('audit_user'))
    except tokens.TokenError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'token': made, 'secret': secret}), 201


@bp.route('/api/settings/api-tokens/<token_id>', methods=['DELETE'])
def revoke_token(token_id):
    try:
        return jsonify(tokens.revoke(token_id))
    except tokens.TokenError as exc:
        return jsonify({'error': str(exc)}), 404
