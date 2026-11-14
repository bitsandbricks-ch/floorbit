"""Sign in with Discord (OAuth2 authorization code flow).

Set up under Settings > Discord sign-in. With only the client ID and secret, Discord sign-in
works for accounts an admin linked to a Discord user. With a server (guild) ID, members of
that server can also sign in on their own: their server roles decide whether they get in and
with which Floorbit role, and an account is created on their first sign-in. See docs/auth.md.
"""
from urllib.parse import urlencode

import requests

from .base import AuthError, Identity, RedirectProvider

AUTHORIZE_URL = 'https://discord.com/oauth2/authorize'
API = 'https://discord.com/api/v10'
TIMEOUT = 10

# Setting keys, read through ``settings(key)`` on every request so a save applies at once.
CLIENT_ID = 'signin.discord_client_id'
CLIENT_SECRET = 'signin.discord_client_secret'
GUILD_ID = 'signin.discord_guild_id'
ROLE_KEYS = (('admin', 'signin.discord_admin_roles'),
             ('editor', 'signin.discord_editor_roles'),
             ('viewer', 'signin.discord_viewer_roles'))


class DiscordProvider(RedirectProvider):
    id = 'discord'
    label = 'Discord'

    def __init__(self, settings):
        self.settings = settings

    def _get(self, key):
        try:
            return self.settings(key)
        except KeyError:
            return None

    def enabled(self):
        return bool(self._get(CLIENT_ID) and self._get(CLIENT_SECRET))

    @property
    def guild_id(self):
        return str(self._get(GUILD_ID) or '').strip()

    @property
    def auto_create_users(self):
        # Only a server limits who can sign in, so only then may a stranger get an account.
        return bool(self.guild_id)

    def start(self, callback_url, state):
        scope = 'identify' + (' guilds.members.read' if self.guild_id else '')
        query = urlencode({
            'response_type': 'code',
            'client_id': self._get(CLIENT_ID),
            'scope': scope,
            'state': state,
            'redirect_uri': callback_url,
            'prompt': 'none',
        })
        return f'{AUTHORIZE_URL}?{query}'

    def finish(self, request, callback_url):
        if request.args.get('error'):
            raise AuthError('Discord sign-in was cancelled.')
        code = request.args.get('code')
        if not code:
            raise AuthError('Discord sent no sign-in code. Please try again.')
        token = self._token(code, callback_url)
        headers = {'Authorization': f'Bearer {token}'}
        me = self._call('GET', '/users/@me', headers=headers)
        identity = Identity(provider=self.id, subject=str(me['id']), username=me.get('username') or '',
                            display_name=me.get('global_name') or me.get('username') or '')
        if self.guild_id:
            resp = self._call('GET', f'/users/@me/guilds/{self.guild_id}/member', headers=headers,
                              allow_missing=True)
            identity.claims = {'member': resp is not None, 'roles': [str(r) for r in (resp or {}).get('roles', [])]}
            if resp and resp.get('nick'):
                identity.display_name = resp['nick']
        return identity

    # Who gets in -----------------------------------------------------------------------
    def role_for(self, identity):
        """The Floorbit role a server member gets, or None when their roles don't let them in."""
        if not self.guild_id or not identity.claims.get('member'):
            return None
        mapped = {name: set(self._get(key) or []) for name, key in ROLE_KEYS}
        if not any(mapped.values()):
            return 'viewer'   # no role lists: every member of the server may look
        have = set(identity.claims.get('roles') or [])
        return next((name for name, ids in mapped.items() if ids & have), None)

    def new_user_role(self, identity):
        role = self.role_for(identity)
        if role is None:
            raise AuthError('Your Discord account is not in a server role that can sign in here. '
                            'Ask an organiser.')
        return role

    def check_existing(self, user, identity):
        # Accounts this provider created stop working once the person leaves the server or role.
        # Accounts an admin linked by hand are trusted as they are.
        if user.get('created_by') == self.id and self.guild_id and self.role_for(identity) is None:
            raise AuthError('Your Discord account is no longer in a server role that can sign in here.')

    # HTTP --------------------------------------------------------------------------------
    def _token(self, code, callback_url):
        body = self._call('POST', '/oauth2/token', data={
            'grant_type': 'authorization_code', 'code': code, 'redirect_uri': callback_url,
        }, auth=(self._get(CLIENT_ID), self._get(CLIENT_SECRET)))
        token = body.get('access_token')
        if not token:
            raise AuthError('Discord did not accept the sign-in. Please try again.')
        return token

    def _call(self, method, path, allow_missing=False, **kwargs):
        try:
            resp = requests.request(method, API + path, timeout=TIMEOUT, **kwargs)
        except requests.RequestException:
            raise AuthError('Discord could not be reached. Please try again.') from None
        if allow_missing and resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            # 400/401 on the token call: wrong secret or redirect URL. Log it for the admin.
            print(f'[auth] Discord {method} {path.split("?")[0]} returned {resp.status_code}')
            raise AuthError('Discord sign-in failed. If this keeps happening, ask an admin to check '
                            'the Discord sign-in settings.')
        try:
            return resp.json()
        except ValueError:
            raise AuthError('Discord sent an answer this app does not understand.') from None
