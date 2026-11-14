"""Sign in with OpenID Connect providers (Authentik, Keycloak, Entra ID, Google, ...). See docs/auth.md.

Admins add providers under Settings > Sign-in providers; they are stored in data.json under
``auth_oidc``. The client secret never is: it comes from ``OIDC_<ID>_CLIENT_SECRET`` or the file
named in ``OIDC_<ID>_CLIENT_SECRET_FILE`` (a Docker secret), so a backup or a leaked data.json holds
no credentials.

The flow is the authorization code flow with PKCE (S256), ``state`` (checked in auth/__init__.py)
and ``nonce``. The ID token's signature is checked against the issuer's JWKS, and so are ``iss``,
``aud``, ``azp``, ``exp`` and ``nonce``. Only https issuers are accepted, except localhost.
"""
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit

import jwt
import requests
from flask import session

from . import roles
from .providers.base import AuthError, Identity, RedirectProvider

KEY = 'auth_oidc'
PREFIX = 'oidc-'               # provider ids in URLs and on accounts: oidc-<id>
ID_RE = re.compile(r'^[a-z][a-z0-9]{1,23}$')
DEFAULT_SCOPES = 'openid profile email'
DEFAULT_CLAIM = 'groups'
MAX_PROVIDERS = 10
TIMEOUT = 10
DISCOVERY_TTL = 3600
# Asymmetric algorithms only: "none" and HS* (signed with the client secret) are never accepted.
ALGORITHMS = ('RS256', 'RS384', 'RS512', 'PS256', 'PS384', 'PS512', 'ES256', 'ES384', 'ES512', 'EdDSA')
LEEWAY = 60                    # seconds of clock skew allowed on exp / iat

_lock = threading.Lock()
_path = None
_discovery = {}                # issuer -> (fetched_at, config, jwks)


class OIDCError(ValueError):
    pass


def configure(path_getter):
    global _path
    _path = path_getter


# storage --------------------------------------------------------------------------------------
def _read():
    path = _path() if _path else None
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _write(data):
    with open(_path(), 'w') as f:   # in place: data.json is bind-mounted
        json.dump(data, f, indent=2)


def all_configs():
    raw = _read().get(KEY) or {}
    return {k: v for k, v in raw.items() if isinstance(v, dict) and ID_RE.match(k)}


def env_name(provider_id):
    return f'OIDC_{provider_id.upper()}_CLIENT_SECRET'


def client_secret(provider_id):
    name = env_name(provider_id)
    if os.environ.get(name):
        return os.environ[name]
    path = os.environ.get(name + '_FILE')
    if path:
        try:
            with open(path) as f:
                return f.read().strip() or None
        except OSError:
            print(f'[auth] {name}_FILE could not be read')
    return None


def check_issuer(url):
    url = (url or '').strip().rstrip('/')
    parts = urlsplit(url)
    local = parts.hostname in ('localhost', '127.0.0.1', '::1')
    if not parts.hostname or parts.query or parts.fragment or parts.username or parts.password:
        raise OIDCError('The issuer is a URL like https://auth.example.com/application/o/floorbit.')
    if parts.scheme != 'https' and not (parts.scheme == 'http' and local):
        raise OIDCError('The issuer must use https (http only for localhost).')
    return url


def _clean_mapping(rules):
    out = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            raise OIDCError('Each role mapping is a claim value and a role.')
        value = str(rule.get('value') or '').strip()[:200]
        if not value:
            continue
        try:
            role = roles.validate(rule.get('role'))
        except roles.RoleError as exc:
            raise OIDCError(str(exc)) from None
        out.append({'value': value, 'role': role})
    return out[:50]


def save(provider_id, body):
    provider_id = (provider_id or '').strip().lower()
    if not ID_RE.match(provider_id):
        raise OIDCError('A provider ID is 2 to 24 lowercase letters or digits, starting with a letter.')
    name = (body.get('name') or '').strip()[:40]
    if not name or re.search(r'[\x00-\x1f<>]', name):
        raise OIDCError('Give the provider a name for its button, up to 40 characters.')
    client_id = (body.get('client_id') or '').strip()
    if not client_id or len(client_id) > 200:
        raise OIDCError('Enter the client ID from your identity provider.')
    scopes = ' '.join((body.get('scopes') or DEFAULT_SCOPES).split())
    if 'openid' not in scopes.split():
        raise OIDCError('The scopes must include openid.')
    claim = (body.get('role_claim') or DEFAULT_CLAIM).strip()[:64]
    config = {'name': name, 'issuer': check_issuer(body.get('issuer')), 'client_id': client_id,
              'scopes': scopes[:300], 'role_claim': claim, 'role_mapping': _clean_mapping(body.get('role_mapping'))}
    with _lock:
        data = _read()
        stored = {k: v for k, v in (data.get(KEY) or {}).items() if isinstance(v, dict)}
        if provider_id not in stored and len(stored) >= MAX_PROVIDERS:
            raise OIDCError(f'At most {MAX_PROVIDERS} sign-in providers.')
        stored[provider_id] = config
        data[KEY] = stored
        _write(data)
    _discovery.pop(config['issuer'], None)
    return config


def delete(provider_id):
    with _lock:
        data = _read()
        stored = data.get(KEY) or {}
        if provider_id not in stored:
            raise OIDCError(f'No sign-in provider called {provider_id}.')
        del stored[provider_id]
        data[KEY] = stored
        _write(data)


def providers():
    return [OIDCProvider(pid, cfg) for pid, cfg in sorted(all_configs().items())]


# discovery ------------------------------------------------------------------------------------
def _get_json(url, what):
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={'Accept': 'application/json'})
    except requests.RequestException:
        raise AuthError(f'The sign-in provider could not be reached ({what}). Please try again.') from None
    if resp.status_code >= 400:
        print(f'[auth] OIDC {what} {url} returned {resp.status_code}')
        raise AuthError('The sign-in provider is not answering correctly. Ask an admin to check its settings.')
    try:
        return resp.json()
    except ValueError:
        raise AuthError('The sign-in provider sent an answer this app does not understand.') from None


def discover(issuer, refresh=False):
    """The issuer's configuration and keys, cached for an hour."""
    cached = _discovery.get(issuer)
    if cached and not refresh and time.time() - cached[0] < DISCOVERY_TTL:
        return cached[1], cached[2]
    config = _get_json(issuer + '/.well-known/openid-configuration', 'discovery')
    # The document must name the same issuer, or tokens from another issuer could pass.
    if str(config.get('issuer') or '').rstrip('/') != issuer:
        raise AuthError('The sign-in provider names a different issuer. Ask an admin to check the issuer URL.')
    for key in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
        url = config.get(key) or ''
        try:
            check_issuer(url.split('?')[0])
        except OIDCError:
            raise AuthError(f'The sign-in provider sent an unsafe {key}.') from None
    jwks = _get_json(config['jwks_uri'], 'keys')
    _discovery[issuer] = (time.time(), config, jwks)
    return config, jwks


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


# the provider ---------------------------------------------------------------------------------
class OIDCProvider(RedirectProvider):
    def __init__(self, provider_id, config):
        self.config_id = provider_id
        self.id = PREFIX + provider_id
        self.label = config['name']
        self.config = config

    def enabled(self):
        return bool(client_secret(self.config_id))

    @property
    def mapping(self):
        return self.config.get('role_mapping') or []

    @property
    def auto_create_users(self):
        # Without a mapping nobody is let in on their own: only accounts an admin linked.
        return bool(self.mapping)

    def start(self, callback_url, state):
        config, _ = discover(self.config['issuer'])
        verifier = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(24)
        session['oidc'] = {'provider': self.id, 'verifier': verifier, 'nonce': nonce}
        query = urlencode({
            'response_type': 'code',
            'client_id': self.config['client_id'],
            'scope': self.config.get('scopes') or DEFAULT_SCOPES,
            'redirect_uri': callback_url,
            'state': state,
            'nonce': nonce,
            'code_challenge': _b64(hashlib.sha256(verifier.encode()).digest()),
            'code_challenge_method': 'S256',
        })
        sep = '&' if '?' in config['authorization_endpoint'] else '?'
        return config['authorization_endpoint'] + sep + query

    def finish(self, request, callback_url):
        pending = session.pop('oidc', None) or {}
        if request.args.get('error'):
            raise AuthError(f'{self.label} sign-in was cancelled.')
        code = request.args.get('code')
        if not code or pending.get('provider') != self.id:
            raise AuthError('The sign-in link expired. Please try again.')
        config, jwks = discover(self.config['issuer'])
        tokens = self._token(config, code, callback_url, pending['verifier'])
        claims = self._verify(tokens.get('id_token'), config, jwks, pending['nonce'])
        claim = self.config.get('role_claim') or DEFAULT_CLAIM
        if self.mapping and claim not in claims and config.get('userinfo_endpoint') and tokens.get('access_token'):
            claims = {**self._userinfo(config, tokens['access_token'], claims['sub']), **claims}
        return Identity(provider=self.id, subject=str(claims['sub']),
                        username=claims.get('preferred_username') or (claims.get('email') or '').split('@')[0],
                        display_name=claims.get('name') or claims.get('preferred_username') or '',
                        email=claims.get('email') or '', claims=claims)

    # Who gets in -----------------------------------------------------------------------
    def role_for(self, identity):
        """The highest mapped role (most permissions) the person's claim values give, or None."""
        have = identity.claims.get(self.config.get('role_claim') or DEFAULT_CLAIM)
        if isinstance(have, str):
            have = [have]
        have = {str(v) for v in have or []} if isinstance(have, list) else set()
        matches = [r['role'] for r in self.mapping if r['value'] in have and r['role'] in roles.all_roles()]
        if not matches:
            return None
        return max(matches, key=lambda r: len(roles.permissions_of(r)))   # ties: first rule wins

    def new_user_role(self, identity):
        role = self.role_for(identity)
        if role is None:
            raise AuthError(f'Your {self.label} account is not in a group that can sign in here. Ask an organiser.')
        return role

    def check_existing(self, user, identity):
        # Accounts this provider created stop working once the person loses every mapped group.
        if user.get('created_by') == self.id and self.role_for(identity) is None:
            raise AuthError(f'Your {self.label} account is no longer in a group that can sign in here.')

    # HTTP --------------------------------------------------------------------------------
    def _token(self, config, code, callback_url, verifier):
        secret = client_secret(self.config_id)
        form = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': callback_url,
                'code_verifier': verifier}
        methods = config.get('token_endpoint_auth_methods_supported') or ['client_secret_basic']
        kwargs = {}
        if 'client_secret_basic' in methods:
            kwargs['auth'] = (self.config['client_id'], secret)
        else:
            form.update(client_id=self.config['client_id'], client_secret=secret)
        try:
            resp = requests.post(config['token_endpoint'], data=form, timeout=TIMEOUT,
                                 headers={'Accept': 'application/json'}, **kwargs)
        except requests.RequestException:
            raise AuthError(f'{self.label} could not be reached. Please try again.') from None
        if resp.status_code >= 400:
            print(f'[auth] OIDC {self.id} token call returned {resp.status_code}')
            raise AuthError(f'{self.label} did not accept the sign-in. If this keeps happening, '
                            'ask an admin to check the client ID, secret and redirect URL.')
        try:
            return resp.json()
        except ValueError:
            raise AuthError(f'{self.label} sent an answer this app does not understand.') from None

    def _key(self, token, jwks, config):
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise AuthError(f'{self.label} sent an ID token this app cannot read.') from None
        alg = header.get('alg')
        allowed = set(config.get('id_token_signing_alg_values_supported') or ['RS256']) & set(ALGORITHMS)
        if alg not in allowed:
            raise AuthError(f'{self.label} signed the ID token with {alg}, which this app does not accept.')
        kid = header.get('kid')
        for refreshed in (False, True):
            if refreshed:   # the issuer may have rotated its keys since we cached them
                _, jwks = discover(self.config['issuer'], refresh=True)
            try:
                keys = jwt.PyJWKSet.from_dict(jwks).keys
            except jwt.PyJWTError:
                keys = []
            usable = [k for k in keys if (kid is None or k.key_id == kid)
                      and (getattr(k, 'public_key_use', None) in (None, 'sig'))]
            if usable:
                return usable[0], alg
        raise AuthError(f'{self.label} signed the ID token with a key it does not publish.')

    def _verify(self, token, config, jwks, nonce):
        if not token:
            raise AuthError(f'{self.label} sent no ID token. Check that the scopes include openid.')
        key, alg = self._key(token, jwks, config)
        try:
            claims = jwt.decode(token, key=key.key, algorithms=[alg], audience=self.config['client_id'],
                                issuer=config['issuer'], leeway=LEEWAY,
                                options={'require': ['exp', 'iat', 'iss', 'aud', 'sub']})
        except jwt.ExpiredSignatureError:
            raise AuthError('The sign-in took too long. Please try again.') from None
        except jwt.PyJWTError as exc:
            print(f'[auth] OIDC {self.id} ID token refused: {exc}')
            raise AuthError(f'{self.label} sent an ID token that does not check out.') from None
        aud = claims['aud'] if isinstance(claims['aud'], list) else [claims['aud']]
        if len(aud) > 1 and claims.get('azp') != self.config['client_id']:
            raise AuthError(f'{self.label} sent an ID token meant for another app.')
        if not secrets.compare_digest(str(claims.get('nonce') or ''), nonce):
            raise AuthError('The sign-in link expired. Please try again.')
        return claims

    def _userinfo(self, config, access_token, sub):
        try:
            resp = requests.get(config['userinfo_endpoint'], timeout=TIMEOUT,
                                headers={'Authorization': f'Bearer {access_token}', 'Accept': 'application/json'})
            info = resp.json() if resp.status_code < 400 else {}
        except (requests.RequestException, ValueError):
            info = {}
        # Only trust it about the same person the signed ID token named.
        return info if isinstance(info, dict) and str(info.get('sub')) == str(sub) else {}
