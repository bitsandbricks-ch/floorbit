"""What a login method has to provide.

Two shapes cover what we need:

- ``PasswordProvider``: the login form posts a username and password and the
  provider checks them (local accounts today, LDAP would fit here too).
- ``RedirectProvider``: the login page shows a button, the browser is sent to
  an outside service and comes back to ``/auth/<id>/callback`` (OIDC / SSO,
  Discord OAuth). The provider turns that callback into an ``Identity``, and
  ``auth.resolve_identity`` maps it to a local user.

Register a provider with ``app.extensions['auth'].providers.register(MyProvider())``,
or in ``Auth.__init__`` when its env vars are set.
"""
from dataclasses import dataclass, field


@dataclass
class Identity:
    """Who an outside service says the person is."""
    provider: str
    subject: str                     # stable id at the provider (OIDC "sub", Discord user id)
    username: str = ''               # suggestion for a new local account
    display_name: str = ''
    email: str = ''
    claims: dict = field(default_factory=dict)


class AuthError(Exception):
    """Shown to the person on the login page."""


class AuthProvider:
    id = ''                          # url-safe, used in /auth/<id>/...
    label = ''                       # button text, "Sign in with <label>"
    kind = ''                        # 'password' or 'redirect'

    def enabled(self):
        return True


class PasswordProvider(AuthProvider):
    kind = 'password'

    def authenticate(self, username, password):
        """Return a user record (see auth.users) or None."""
        raise NotImplementedError


class RedirectProvider(AuthProvider):
    kind = 'redirect'
    # A first login from someone without a linked account creates one. Keep it
    # off unless the provider itself limits who can sign in (e.g. a guild role).
    auto_create_users = False
    default_role = 'viewer'          # role of an account created that way

    def start(self, callback_url, state):
        """URL to send the browser to. ``state`` must come back on the callback."""
        raise NotImplementedError

    def finish(self, request, callback_url):
        """Turn the callback request into an Identity, or raise AuthError."""
        raise NotImplementedError
