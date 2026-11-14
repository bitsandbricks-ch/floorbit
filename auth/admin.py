"""Account management: the /settings/users page, roles and teams, and their API.

The guard in auth/__init__.py already limits these paths to accounts with ``accounts.manage``
(roles.RULES), so the views only check what is specific to accounts.

- ``GET /api/roles``: every permission and role; ``PUT``/``DELETE /api/roles/<id>`` for custom roles.
- ``GET /api/teams``: the team tree with members; ``POST /api/teams``, ``PATCH``/``DELETE
  /api/teams/<id>``; ``PUT``/``DELETE /api/teams/<id>/members/<username>`` (``{"role": ...}``).
- ``GET /api/settings/oidc``: OIDC sign-in providers (never their secrets); ``PUT``/``DELETE
  /api/settings/oidc/<id>``, ``POST .../<id>/test``. These need ``settings.manage``.
"""
from flask import Blueprint, jsonify, render_template, request

from floorbit import spa

from . import oidc, roles, teams
from .providers import AuthError
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
            # Providers an admin can link accounts to (configured, even if the secret is missing).
            'oidc': [{'id': oidc.PREFIX + pid, 'label': cfg['name']}
                     for pid, cfg in sorted(oidc.all_configs().items())],
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
            if 'identity' in body:
                link = body['identity'] if isinstance(body['identity'], dict) else {}
                provider = str(link.get('provider') or '')
                if provider[len(oidc.PREFIX):] not in oidc.all_configs() or not provider.startswith(oidc.PREFIX):
                    raise UserError('Pick one of the sign-in providers.')
                subject = str(link.get('subject') or '').strip()
                if len(subject) > 255:
                    raise UserError('That subject is too long.')
                auth.users.link_identity(username, provider, subject)
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

    # OIDC sign-in providers ----------------------------------------------------------------
    def oidc_payload():
        return {
            'providers': [{'id': pid, **cfg, 'secret_env': oidc.env_name(pid),
                           'secret_set': bool(oidc.client_secret(pid)),
                           'callback_url': auth.callback_url(oidc.PREFIX + pid)}
                          for pid, cfg in sorted(oidc.all_configs().items())],
            'roles': [{'id': r, 'label': v['label']} for r, v in roles.all_roles().items()],
            # The redirect URL a new provider will have: replace ID with its ID.
            'callback_template': auth.callback_url(oidc.PREFIX + 'ID'),
        }

    @bp.route('/settings/sign-in')
    def oidc_page():
        return spa.render('Sign-in providers')

    @bp.route('/api/settings/oidc', methods=['GET'])
    def oidc_list():
        return jsonify(oidc_payload())

    @bp.route('/api/settings/oidc/<provider_id>', methods=['PUT'])
    def oidc_save(provider_id):
        try:
            oidc.save(provider_id, request.get_json(silent=True) or {})
        except oidc.OIDCError as exc:
            return error(exc)
        return jsonify({'id': provider_id, **oidc_payload()})

    @bp.route('/api/settings/oidc/<provider_id>', methods=['DELETE'])
    def oidc_delete(provider_id):
        try:
            oidc.delete(provider_id)
        except oidc.OIDCError as exc:
            return error(exc)
        return jsonify({'id': provider_id, **oidc_payload()})

    @bp.route('/api/settings/oidc/<provider_id>/test', methods=['POST'])
    def oidc_test(provider_id):
        cfg = oidc.all_configs().get(provider_id)
        if not cfg:
            return error(f'No sign-in provider called {provider_id}.', 404)
        try:
            config, jwks = oidc.discover(cfg['issuer'], refresh=True)
        except AuthError as exc:
            return jsonify({'ok': False, 'error': str(exc)})
        problems = []
        if 'S256' not in (config.get('code_challenge_methods_supported') or ['S256']):
            problems.append('The provider does not list PKCE (S256).')
        if not oidc.client_secret(provider_id):
            problems.append(f'{oidc.env_name(provider_id)} is not set on the server.')
        return jsonify({'ok': not problems, 'problems': problems, 'keys': len(jwks.get('keys') or []),
                        'authorization_endpoint': config['authorization_endpoint']})

    return bp
