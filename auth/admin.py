"""Account management for admins: the /settings/users page and its API.

The guard in auth/__init__.py already limits these paths to admins
(roles.ADMIN_PATHS), so the views only check what is specific to accounts.
"""
from flask import Blueprint, jsonify, render_template, request

from . import roles
from .users import UserError, public


def create_users_blueprint(auth):
    bp = Blueprint('users', __name__)

    def me():
        from . import current_user
        return current_user()

    def payload():
        return {
            'users': auth.users.list(),
            'roles': [{'id': r, 'label': roles.LABELS[r], 'description': roles.DESCRIPTIONS[r]}
                      for r in roles.ROLES],
            'me': (me() or {}).get('username'),
        }

    def error(exc, status=400):
        return jsonify({'error': str(exc)}), status

    @bp.route('/settings/users')
    def users_page():
        return render_template('users.html')

    @bp.route('/api/users', methods=['GET'])
    def list_users():
        return jsonify(payload())

    @bp.route('/api/users', methods=['POST'])
    def add_user():
        body = request.get_json(silent=True) or {}
        try:
            auth.users.add(body.get('username'), body.get('password') or '',
                           display_name=body.get('display_name'), role=body.get('role') or roles.DEFAULT_ROLE)
        except UserError as exc:
            return error(exc)
        return jsonify(payload()), 201

    @bp.route('/api/users/<username>', methods=['PATCH'])
    def update_user(username):
        body = request.get_json(silent=True) or {}
        current = me() or {}
        try:
            if body.get('role') and username.lower() == current.get('username', '').lower() \
                    and body['role'] != current.get('role'):
                raise UserError('You cannot change your own role. Ask another admin.')
            if 'role' in body or 'display_name' in body:
                auth.users.update(username, role=body.get('role'), display_name=body.get('display_name'))
            if body.get('password'):
                auth.users.set_password(username, body['password'])
        except UserError as exc:
            return error(exc)
        user = auth.users.get(username)
        return jsonify({'user': public(user) if user else None, **payload()})

    @bp.route('/api/users/<username>', methods=['DELETE'])
    def remove_user(username):
        if username.lower() == ((me() or {}).get('username') or '').lower():
            return error('You cannot remove your own account.')
        try:
            auth.users.remove(username)
        except UserError as exc:
            return error(exc)
        return jsonify(payload())

    return bp
