"""Account management: the /settings/users page, roles and teams, and their API.

The guard in auth/__init__.py already limits these paths to accounts with ``accounts.manage``
(roles.RULES), so the views only check what is specific to accounts.

- ``GET /api/roles``: every permission and role; ``PUT``/``DELETE /api/roles/<id>`` for custom roles.
- ``GET /api/teams``: the team tree with members; ``POST /api/teams``, ``PATCH``/``DELETE
  /api/teams/<id>``; ``PUT``/``DELETE /api/teams/<id>/members/<username>`` (``{"role": ...}``).
"""
from flask import Blueprint, jsonify, render_template, request

from floorbit import spa

from . import roles, teams
from .users import UserError, public


def create_users_blueprint(auth):
    bp = Blueprint('users', __name__)

    def me():
        from . import current_user
        return current_user()

    def payload():
        return {
            'users': auth.users.list(),
            'roles': [{'id': r, 'label': v['label'], 'description': v['description']}
                      for r, v in roles.all_roles().items()],
            'me': (me() or {}).get('username'),
            'discord': bool(auth.providers.get('discord')),
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
            if 'discord_id' in body:
                discord_id = str(body['discord_id'] or '').strip()
                if discord_id and not (discord_id.isdigit() and 17 <= len(discord_id) <= 20):
                    raise UserError('A Discord user ID is a number of 17 to 20 digits. In Discord, '
                                    'turn on developer mode, right-click the person and copy their ID.')
                auth.users.link_identity(username, 'discord', discord_id)
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

    # roles ----------------------------------------------------------------------------------
    def roles_payload():
        users = auth.users.list()
        return {
            'permissions': [{'id': p, 'label': text} for p, text in roles.PERMISSIONS.items()],
            'roles': [{'id': r, **v, 'users': sum(1 for u in users if u['role'] == r)}
                      for r, v in roles.all_roles().items()],
        }

    @bp.route('/api/roles', methods=['GET'])
    def list_roles():
        return jsonify(roles_payload())

    @bp.route('/api/roles/<role_id>', methods=['PUT'])
    def save_role(role_id):
        body = request.get_json(silent=True) or {}
        perms = body.get('permissions')
        try:
            if not isinstance(perms, list):
                raise roles.RoleError('permissions must be a list.')
            roles.save(role_id, body.get('label'), body.get('description', ''), perms)
        except roles.RoleError as exc:
            return error(exc)
        return jsonify({'id': role_id, **roles_payload()})

    @bp.route('/api/roles/<role_id>', methods=['DELETE'])
    def delete_role(role_id):
        try:
            roles.delete(role_id)
        except roles.RoleError as exc:
            return error(exc)
        return jsonify({'id': role_id, **roles_payload()})

    # teams ----------------------------------------------------------------------------------
    def teams_payload():
        return {'teams': teams.tree()}

    @bp.route('/settings/teams')
    def teams_page():
        return spa.render('Roles and teams')

    @bp.route('/api/teams', methods=['GET'])
    def list_teams():
        return jsonify(teams_payload())

    @bp.route('/api/teams', methods=['POST'])
    def add_team():
        body = request.get_json(silent=True) or {}
        try:
            team = teams.create(body.get('name'), body.get('parent'))
        except teams.TeamError as exc:
            return error(exc)
        return jsonify({'id': team['id'], **teams_payload()}), 201

    @bp.route('/api/teams/<team_id>', methods=['PATCH'])
    def update_team(team_id):
        body = request.get_json(silent=True) or {}
        try:
            teams.update(team_id, name=body.get('name'), parent=body.get('parent', ...))
        except teams.TeamError as exc:
            return error(exc)
        return jsonify({'id': team_id, **teams_payload()})

    @bp.route('/api/teams/<team_id>', methods=['DELETE'])
    def delete_team(team_id):
        try:
            teams.delete(team_id)
        except teams.TeamError as exc:
            return error(exc)
        return jsonify({'id': team_id, **teams_payload()})

    @bp.route('/api/teams/<team_id>/members/<username>', methods=['PUT', 'DELETE'])
    def team_member(team_id, username):
        role = None if request.method == 'DELETE' else (request.get_json(silent=True) or {}).get('role')
        try:
            if request.method == 'PUT' and not role:
                raise teams.TeamError('Pick a role for this team.')
            teams.set_member(username, team_id, role)
        except teams.TeamError as exc:
            return error(exc)
        return jsonify({'id': team_id, 'username': username, **teams_payload()})

    return bp
