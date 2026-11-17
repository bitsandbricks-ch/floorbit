"""Sign-in for the floor plan.

``init_auth(app, data_file)`` adds the login page, the session cookie and a
guard that runs before every request:

- Always open: the login page, static files, and the paths in
  ``AUTH_PUBLIC_PATHS`` (the attendee check-in page and the kiosk view).
- Open while ``AUTH_PUBLIC_READ`` is on (the default): read-only ``GET``
  requests to ``/api/...``, so a kiosk screen can show the floor plan without
  an account. ``/api/settings`` and ``/api/users`` are never open.
- Everything else, which is every page of the editor, ``/settings`` and every
  request that changes something, needs a signed-in user whose role has the
  permission the request needs (see roles.py: roles are sets of permissions,
  and every path has a rule; a path without one needs an admin to change it).

How a person proves who they are is up to the providers in ``providers/``:
local username and password accounts and Discord (providers/discord.py).
"""
import os
import re
import secrets
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, session, url_for

from . import oidc, roles, teams, tokens
from .admin import create_users_blueprint
from .providers import AuthError, Identity, LocalProvider, Registry
from .users import UserError, UserStore, clean_nav, public

__all__ = ['Auth', 'AuthError', 'Identity', 'current_user', 'init_auth', 'login_required', 'public_endpoint']

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')
DEFAULT_PUBLIC_PATHS = '/checkin,/api/checkin,/kiosk'
# What AUTH_PUBLIC_READ opens to someone not signed in: what the kiosk view and the big screens
# draw (static/js/kiosk.js), and nothing else. Anything more (inventory with management IPs,
# incidents, the firewall per seat, reports) needs an account. A path covers what is below it.
PUBLIC_READ_PATHS = ('/api/auth/me', '/api/plugins/menu',   # answer for "nobody" themselves
                     '/api/config', '/api/version', '/api/features', '/api/halls', '/api/plan-marks',
                     '/api/seat-blocks', '/api/seats/occupancy', '/api/stats/seats', '/api/status/snapshot',
                     '/api/switches', '/api/events')
PUBLIC_READ_EXACT = ('/api/seats',)    # not /api/seats/info and the rest below it
MAX_FAILURES = 5                 # per address and username ...
FAILURE_WINDOW = 300             # ... within this many seconds
MAX_FAILURE_KEYS = 10000         # address/username pairs remembered before stale ones are dropped


def _env_bool(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == '':
        return default
    return raw.strip().lower() not in ('false', '0', 'no', 'off')


def _env_list(name, default):
    raw = os.environ.get(name)
    raw = default if raw is None else raw
    return [p.strip().rstrip('/') or '/' for p in raw.split(',') if p.strip()]


def public_endpoint(view):
    """Mark a view as open to everyone, whatever the path rules say."""
    view._auth_public = True
    return view


def login_required(view):
    """For views that must stay protected even under a public path."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return _deny()
        return view(*args, **kwargs)
    return wrapper


def current_user():
    """The signed-in user's public record, or None."""
    if 'auth_user' not in g:
        g.auth_user = _load_session_user()
    return g.auth_user


def _auth():
    return current_app.extensions['auth']


def _load_session_user():
    auth = current_app.extensions.get('auth')
    if not auth or not auth.enabled:
        return None
    token = tokens.bearer(request.headers)
    if token is not None:   # a script with an API token: the session cookie doesn't count
        record = tokens.check(token)
        return tokens.as_user(record) if record else None
    username = session.get('user')
    if not username:
        return None
    user = auth.users.get(username)
    # A password change bumps session_version, which signs out old sessions.
    if not user or user.get('session_version', 1) != session.get('ver'):
        session.clear()
        return None
    return public(user)


def _safe_next(target):
    """Only redirect back to a path on this site."""
    if not target:
        return '/'
    parts = urlsplit(target)
    # Browsers read a backslash as a slash, so /\evil.example would leave the site too.
    if parts.scheme or parts.netloc or not target.startswith('/') or target[1:2] in ('/', '\\'):
        return '/'
    return target


def _wants_json():
    if request.path.startswith('/api/'):
        return True
    best = request.accept_mimetypes.best_match(['text/html', 'application/json'])
    return best == 'application/json'


def _deny():
    if _wants_json():
        return jsonify({'error': 'Sign in required', 'login_url': url_for('auth.login')}), 401
    return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))


def _forbidden(needed):
    what = roles.PERMISSIONS.get(needed, needed)
    message = f'Your role can\'t do this. It needs the permission: {what[0].lower() + what[1:]}.'
    if _wants_json():
        return jsonify({'error': message, 'permission_needed': needed}), 403
    return render_template('forbidden.html', message=message, user=current_user()), 403


def _same_origin():
    """Refuse state changes posted from another site (CSRF), on top of SameSite cookies."""
    origin = request.headers.get('Origin')
    if origin:
        if origin == 'null':
            return False
        # Behind a reverse proxy that rewrites Host, X-Forwarded-Host holds the public name.
        hosts = {request.host, request.headers.get('X-Forwarded-Host', '').split(',')[0].strip()}
        return urlsplit(origin).netloc in hosts or origin.rstrip('/') in _auth().trusted_origins
    # Browsers that send no Origin still send Sec-Fetch-Site.
    return request.headers.get('Sec-Fetch-Site', 'same-origin') in ('same-origin', 'none')


class Auth:
    def __init__(self, app, data_file):
        self.enabled = _env_bool('AUTH_ENABLED', True)
        self.public_read = _env_bool('AUTH_PUBLIC_READ', True)
        self.public_paths = _env_list('AUTH_PUBLIC_PATHS', DEFAULT_PUBLIC_PATHS)
        self.trusted_origins = [o.rstrip('/') for o in _env_list('AUTH_TRUSTED_ORIGINS', '')]
        self.users = UserStore(data_file)
        # Roles and teams live in the same file as the accounts (and follow it in tests).
        roles.configure(lambda: self.users.path)
        teams.configure(lambda: self.users.path)
        oidc.configure(lambda: self.users.path)
        tokens.configure(lambda: self.users.path)
        self.providers = Registry()
        self.providers.register(LocalProvider(self.users))
        self.providers.add_source(oidc.providers)
        self._failures = {}
        self.public_url = lambda: ''   # create_app points this at the PUBLIC_URL setting

        self._key_pending = False
        if not app.config.get('SECRET_KEY'):
            app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or self._secret_key_or_stand_in()
        app.config['SESSION_COOKIE_NAME'] = 'floorbit_session'
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        app.config['SESSION_COOKIE_SECURE'] = _env_bool('AUTH_COOKIE_SECURE', False)
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
            hours=float(os.environ.get('AUTH_SESSION_HOURS') or 12))

        app.extensions['auth'] = self
        app.register_blueprint(_blueprint())
        app.register_blueprint(create_users_blueprint(self))
        app.before_request(self._resolve_secret_key)
        app.before_request(self.guard)
        app.context_processor(lambda: {'current_user': current_user(), 'auth_enabled': self.enabled})
        _register_cli(app, self)
        if self.enabled:
            self._bootstrap_admin()

    # setup ---------------------------------------------------------------
    def _secret_key_or_stand_in(self):
        """The stored key; while the database is away at start, a stand-in for this process
        until it is back (``_resolve_secret_key``). Sign-ins need the database anyway."""
        from floorbit.database import DatabaseUnavailable
        try:
            return self._stored_secret_key()
        except DatabaseUnavailable:
            self._key_pending = True
            return secrets.token_hex(32)

    def _resolve_secret_key(self):
        if not self._key_pending:
            return
        from floorbit.database import DatabaseUnavailable
        try:
            current_app.config['SECRET_KEY'] = self._stored_secret_key()
        except DatabaseUnavailable:
            return
        self._key_pending = False

    def _stored_secret_key(self):
        """Without SECRET_KEY, keep a generated one in data.json so sessions survive restarts."""
        path = self.users.path
        from floorbit.store import read_json  # late: floorbit imports auth while it loads
        data = read_json(path, {})
        if not data.get('auth_secret_key'):
            data['auth_secret_key'] = secrets.token_hex(32)
            from floorbit.store import write_json
            write_json(path, data)
        return data['auth_secret_key']

    def _bootstrap_admin(self):
        name = os.environ.get('AUTH_ADMIN_USER', '').strip()
        password = os.environ.get('AUTH_ADMIN_PASSWORD', '')
        try:
            if self.users.count():
                return
            if name and password:
                self.users.add(name, password, role='admin')
                print(f'[auth] Created the first account, {name}, from AUTH_ADMIN_USER.')
            else:
                print('[auth] No accounts yet. Create one with: flask --app app users add <name>')
        except (OSError, ValueError, RuntimeError) as exc:   # RuntimeError: the database is away
            print(f'[auth] Could not create the first account: {exc}')

    # guard ---------------------------------------------------------------
    def is_public(self):
        path = request.path.rstrip('/') or '/'
        if request.endpoint == 'static' or request.endpoint in ('auth.login', 'auth.logout', 'auth.me',
                                                                  'auth.start', 'auth.callback',
                                                                  'auth.login_options', 'auth.login_api'):
            return True
        view = current_app.view_functions.get(request.endpoint)
        if view is not None and getattr(view, '_auth_public', False):
            return True
        if any(path == p or path.startswith(p + '/') for p in self.public_paths):
            return True
        # Reads of admin-only data (settings, accounts) never count as public.
        return bool(self.public_read and request.method in SAFE_METHODS
                    and (path in PUBLIC_READ_EXACT
                         or any(path == p or path.startswith(p + '/') for p in PUBLIC_READ_PATHS))
                    and roles.needed_for(path, request.method, SAFE_METHODS) == 'floorplan.view')

    def guard(self):
        if not self.enabled:
            return None
        if tokens.bearer(request.headers) is not None:
            return self._guard_token()
        if request.path.startswith('/api/agent/v1/'):
            return None   # the local agent: no browser, its key is checked by each view (blueprints/agent.py)
        if request.method not in SAFE_METHODS and not _same_origin():
            abort(403, description='Cross-site request refused.')
        if self.is_public():
            return None
        user = current_user()
        if not user:
            return _deny()
        needed = roles.needed_for(request.path.rstrip('/') or '/', request.method, SAFE_METHODS)
        if not roles.can(user, needed):
            return _forbidden(needed)
        return None

    @staticmethod
    def _guard_token():
        # No same-origin check: a browser can't send another site's Authorization header without CORS,
        # which Floorbit never allows.
        user = current_user()
        if not user:
            return jsonify({'error': 'The API token is wrong, expired or revoked.'}), 401
        path = request.path.rstrip('/') or '/'
        if not path.startswith('/api/') or tokens.blocked(path):
            return jsonify({'error': "API tokens can't be used here."}), 403
        if user['read_only'] and request.method not in SAFE_METHODS:
            return jsonify({'error': 'This API token can only read.'}), 403
        needed = roles.needed_for(path, request.method, SAFE_METHODS)
        if not roles.can(user, needed):
            return _forbidden(needed)
        return None

    # sign-in -------------------------------------------------------------
    def _failure_key(self, username):
        # The real client behind a trusted proxy: else one guesser locks the name for everyone.
        from integrations import checkin
        return (checkin.client_ip() or '?', (username or '').strip().lower()[:200])

    def locked_for(self, username):
        now = time.time()
        recent = [t for t in self._failures.get(self._failure_key(username), []) if now - t < FAILURE_WINDOW]
        if len(recent) < MAX_FAILURES:
            return 0
        return int(FAILURE_WINDOW - (now - recent[0])) + 1

    def record_failure(self, username):
        key = self._failure_key(username)
        now = time.time()
        self._failures[key] = [t for t in self._failures.get(key, []) if now - t < FAILURE_WINDOW] + [now]
        if len(self._failures) > MAX_FAILURE_KEYS:
            # Every made-up username is a new key: forget the stale ones so guessing can't fill memory.
            for stale in [k for k, v in self._failures.items() if now - v[-1] >= FAILURE_WINDOW]:
                self._failures.pop(stale, None)

    def sign_in(self, user, provider_id):
        self._failures.pop(self._failure_key(user['username']), None)
        session.clear()
        session.permanent = True
        session['user'] = user['username']
        session['ver'] = user.get('session_version', 1)
        session['provider'] = provider_id
        g.auth_user = public(user)

    def resolve_identity(self, identity, provider):
        """Map an outside identity to a local user, creating one if the provider allows it."""
        user = self.users.find_by_identity(identity.provider, identity.subject)
        if user:
            provider.check_existing(user, identity)
            return user
        if not getattr(provider, 'auto_create_users', False):
            raise AuthError(f'No account here is linked to this {provider.label} login. '
                            'Ask an organiser to add you.')
        role = provider.new_user_role(identity)
        base = re.sub(r'[^A-Za-z0-9._-]', '', identity.username or '').lstrip('._-')[:28] or identity.provider
        name, n = base, 1
        while self.users.get(name):
            n += 1
            name = f'{base}{n}'
        return self.users.add(name, display_name=identity.display_name or identity.username,
                              identities={identity.provider: identity.subject},
                              role=role, created_by=provider.id)

    def callback_url(self, provider_id):
        """Where the provider sends the browser back. PUBLIC_URL wins behind a reverse proxy."""
        base = (self.public_url() or '').rstrip('/')
        path = url_for('auth.callback', provider_id=provider_id)
        return base + path if base else url_for('auth.callback', provider_id=provider_id, _external=True)


def init_auth(app, data_file):
    return Auth(app, data_file)


# ── Routes ─────────────────────────────────────────────────────────────────────

def _blueprint():
    bp = Blueprint('auth', __name__)

    def render_login(error=None, username='', status=200):
        """The React sign-in page (frontend/src/pages/Login.tsx). An error waits in the session
        until the page asks for it, so a provider's redirect back can show one too."""
        from floorbit import spa
        if error:
            session['login_error'] = {'error': error, 'username': username}
        return spa.render('Sign in')[0], status

    def password_sign_in(username, password):
        """(user, None) or (None, (message, status))."""
        auth = _auth()
        wait = auth.locked_for(username)
        if wait:
            return None, (f'Too many failed attempts. Try again in {wait} seconds.', 429)
        for provider in auth.providers.enabled('password'):
            user = provider.authenticate(username, password)
            if user:
                auth.sign_in(user, provider.id)
                return user, None
        auth.record_failure(username)
        return None, ('Wrong username or password.', 401)

    @bp.route('/login', methods=['GET', 'POST'])
    def login():
        auth = _auth()
        if not auth.enabled:
            return redirect('/')
        if request.method == 'GET':
            if current_user():
                return redirect(_safe_next(request.args.get('next')))
            return render_login()
        # The plain form post still works, for scripts (scripts/screenshots.py, curl).
        username = (request.form.get('username') or '').strip()
        user, failed = password_sign_in(username, request.form.get('password') or '')
        if user:
            return redirect(_safe_next(request.form.get('next')))
        return render_login(failed[0], username, failed[1])

    def checkin_open():
        from integrations import config
        return (config.get_bool('CHECKIN_ENABLED', False)
                and any(r.rule == '/checkin' for r in current_app.url_map.iter_rules()))

    def _checkin_address():
        from integrations import checkin
        return checkin.short_address() or None

    @bp.route('/api/auth/login-options')
    def login_options():
        """What the sign-in page offers, and the error from the last try (once)."""
        auth = _auth()
        nxt = _safe_next(request.args.get('next'))
        last = session.pop('login_error', None) or {}
        error = last.get('error')
        if error:   # a 200 answer, so the German for errors (floorbit/i18n.py) doesn't run by itself
            from floorbit import i18n
            error = i18n.translate(error, i18n.language(request.headers.get('Accept-Language')))
        return jsonify({
            'enabled': auth.enabled,
            'password_login': bool(auth.providers.enabled('password')),
            'providers': [{'id': p.id, 'label': p.label, 'url': url_for('auth.start', provider_id=p.id, next=nxt)}
                          for p in auth.providers.enabled('redirect')],
            'no_users': auth.users.count() == 0,
            'checkin_url': '/checkin' if checkin_open() else None,
            'checkin_address': _checkin_address() if checkin_open() else None,
            'next': nxt,
            'error': error,
            'username': last.get('username') or '',
        })

    @bp.route('/api/auth/login', methods=['POST'])
    def login_api():
        body = request.get_json(silent=True) or {}
        username = str(body.get('username') or '').strip()
        password = body.get('password') if isinstance(body.get('password'), str) else ''
        user, failed = password_sign_in(username, password)
        if not user:
            return jsonify({'error': failed[0]}), failed[1]
        return jsonify({'ok': True, 'next': _safe_next(body.get('next'))})

    @bp.route('/logout', methods=['POST'])
    def logout():
        session.clear()
        return redirect(url_for('auth.login'))

    @bp.route('/api/auth/me')
    def me():
        auth = _auth()
        return jsonify({'enabled': auth.enabled, 'user': current_user()})

    @bp.route('/api/auth/me/nav', methods=['GET', 'PUT'])
    def my_nav():
        """The sidebar's favourites and fold behaviour for the signed-in account."""
        auth = _auth()
        user = current_user()
        if not auth.enabled or not user or user.get('api_token'):
            return jsonify({'error': 'Only a signed-in account keeps sidebar settings.'}), 400
        if request.method == 'GET':
            return jsonify(clean_nav((auth.users.get(user['username']) or {}).get('nav')))
        return jsonify(auth.users.set_nav(user['username'], request.get_json(silent=True) or {}))

    @bp.route('/auth/<provider_id>/start')
    def start(provider_id):
        provider = _auth().providers.get(provider_id)
        if not provider or provider.kind != 'redirect':
            abort(404)
        state = secrets.token_urlsafe(24)
        session['auth_state'] = state
        session['auth_next'] = _safe_next(request.args.get('next'))
        try:
            return redirect(provider.start(_auth().callback_url(provider_id), state))
        except AuthError as exc:   # e.g. an OIDC issuer that is down: local sign-in still works
            return render_login(str(exc), status=502)

    @bp.route('/auth/<provider_id>/callback')
    def callback(provider_id):
        auth = _auth()
        provider = auth.providers.get(provider_id)
        if not provider or provider.kind != 'redirect':
            abort(404)
        expected = session.pop('auth_state', None)
        next_url = session.pop('auth_next', '/')
        if not expected or not secrets.compare_digest(expected, request.args.get('state', '')):
            return render_login('The sign-in link expired. Please try again.', status=400)
        try:
            identity = provider.finish(request, auth.callback_url(provider_id))
            user = auth.resolve_identity(identity, provider)
        except (AuthError, UserError) as exc:
            return render_login(str(exc), status=403)
        auth.sign_in(user, provider.id)
        return redirect(_safe_next(next_url))

    return bp


# ── CLI: flask --app app users ... ─────────────────────────────────────────────

def _register_cli(app, auth):
    import click
    from flask.cli import AppGroup

    users = AppGroup('users', help='Manage the accounts that can sign in.')

    def fail(exc):
        raise click.ClickException(str(exc))

    @users.command('add')
    @click.argument('username')
    @click.option('--display-name', default='', help='Name shown in the top bar.')
    @click.option('--role', default=None,
                  help='admin, lead, tech, viewer, kiosk or a custom role. Defaults to admin for the first '
                       'account, lead after that.')
    @click.password_option(help='Prompted for when left out.')
    def add_user(username, display_name, role, password):
        role = role or ('admin' if auth.users.count() == 0 else roles.DEFAULT_ROLE)
        try:
            auth.users.add(username, password, display_name=display_name, role=role)
        except UserError as exc:
            fail(exc)
        click.echo(f'Added {username} as {role}.')

    @users.command('role')
    @click.argument('username')
    @click.argument('role')
    def set_role(username, role):
        try:
            auth.users.update(username, role=role)
        except UserError as exc:
            fail(exc)
        click.echo(f'{username} is now {role}.')

    @users.command('passwd')
    @click.argument('username')
    @click.password_option(help='Prompted for when left out.')
    def set_password_cmd(username, password):
        try:
            auth.users.set_password(username, password)
        except UserError as exc:
            fail(exc)
        click.echo(f'Changed the password of {username} and signed out their sessions.')

    @users.command('remove')
    @click.argument('username')
    def remove_user(username):
        try:
            auth.users.remove(username)
        except UserError as exc:
            fail(exc)
        click.echo(f'Removed {username}.')

    @users.command('list')
    def list_users():
        rows = auth.users.list()
        if not rows:
            click.echo('No accounts yet.')
        for user in rows:
            extra = ', '.join(user['identities'])
            click.echo(f"{user['username']:<24} {user['role']:<8} {user['display_name']}"
                       + (f'  [{extra}]' if extra else ''))

    app.cli.add_command(users)
