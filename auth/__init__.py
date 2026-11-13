"""Sign-in for the floor plan.

``init_auth(app, data_file)`` adds the login page, the session cookie and a
guard that runs before every request:

- Always open: the login page, static files, and the paths in
  ``AUTH_PUBLIC_PATHS`` (the attendee check-in page and the kiosk view).
- Open while ``AUTH_PUBLIC_READ`` is on (the default): read-only ``GET``
  requests to ``/api/...``, so a kiosk screen can show the floor plan without
  an account. ``/api/settings`` is never open.
- Everything else, which is every page of the editor, ``/settings`` and every
  request that changes something, needs a signed-in user.

How a person proves who they are is up to the providers in ``providers/``;
local username and password accounts are the only one so far.
"""
import os
import re
import secrets
import time
from datetime import timedelta
from functools import wraps
from urllib.parse import urlsplit

from flask import (Blueprint, abort, current_app, g, jsonify, redirect, render_template,
                   request, session, url_for)

from .providers import AuthError, Identity, LocalProvider, Registry
from .users import UserError, UserStore, public

__all__ = ['Auth', 'AuthError', 'Identity', 'current_user', 'init_auth', 'login_required', 'public_endpoint']

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')
DEFAULT_PUBLIC_PATHS = '/checkin,/api/checkin,/kiosk'
MAX_FAILURES = 5                 # per address and username ...
FAILURE_WINDOW = 300             # ... within this many seconds


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
    if parts.scheme or parts.netloc or not target.startswith('/') or target.startswith('//'):
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
        self.providers = Registry()
        self.providers.register(LocalProvider(self.users))
        self._failures = {}

        if not app.config.get('SECRET_KEY'):
            app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or self._stored_secret_key()
        app.config['SESSION_COOKIE_NAME'] = 'lal_session'
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
        app.config['SESSION_COOKIE_SECURE'] = _env_bool('AUTH_COOKIE_SECURE', False)
        app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
            hours=float(os.environ.get('AUTH_SESSION_HOURS') or 12))

        app.extensions['auth'] = self
        app.register_blueprint(_blueprint())
        app.before_request(self.guard)
        app.context_processor(lambda: {'current_user': current_user(), 'auth_enabled': self.enabled})
        _register_cli(app, self)
        if self.enabled:
            self._bootstrap_admin()

    # setup ---------------------------------------------------------------
    def _stored_secret_key(self):
        """Without SECRET_KEY, keep a generated one in data.json so sessions survive restarts."""
        import json
        path = self.users.path
        data = {}
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
        if not data.get('auth_secret_key'):
            data['auth_secret_key'] = secrets.token_hex(32)
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
        return data['auth_secret_key']

    def _bootstrap_admin(self):
        name = os.environ.get('AUTH_ADMIN_USER', '').strip()
        password = os.environ.get('AUTH_ADMIN_PASSWORD', '')
        try:
            if self.users.count():
                return
            if name and password:
                self.users.add(name, password)
                print(f'[auth] Created the first account, {name}, from AUTH_ADMIN_USER.')
            else:
                print('[auth] No accounts yet. Create one with: flask --app app users add <name>')
        except (OSError, ValueError) as exc:
            print(f'[auth] Could not create the first account: {exc}')

    # guard ---------------------------------------------------------------
    def is_public(self):
        path = request.path.rstrip('/') or '/'
        if request.endpoint == 'static' or request.endpoint in ('auth.login', 'auth.logout', 'auth.me',
                                                                  'auth.start', 'auth.callback'):
            return True
        view = current_app.view_functions.get(request.endpoint)
        if view is not None and getattr(view, '_auth_public', False):
            return True
        if any(path == p or path.startswith(p + '/') for p in self.public_paths):
            return True
        if (self.public_read and request.method in SAFE_METHODS and path.startswith('/api/')
                and not (path == '/api/settings' or path.startswith('/api/settings/'))):
            return True
        return False

    def guard(self):
        if not self.enabled:
            return None
        if request.method not in SAFE_METHODS and not _same_origin():
            abort(403, description='Cross-site request refused.')
        if self.is_public():
            return None
        if current_user():
            return None
        return _deny()

    # sign-in -------------------------------------------------------------
    def _failure_key(self, username):
        return (request.remote_addr or '?', (username or '').strip().lower())

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
            return user
        if not getattr(provider, 'auto_create_users', False):
            raise AuthError(f'No account here is linked to this {provider.label} login. '
                            'Ask an organiser to add you.')
        base = re.sub(r'[^A-Za-z0-9._-]', '', identity.username or '').lstrip('._-')[:28] or identity.provider
        name, n = base, 1
        while self.users.get(name):
            n += 1
            name = f'{base}{n}'
        return self.users.add(name, display_name=identity.display_name or identity.username,
                              identities={identity.provider: identity.subject})


def init_auth(app, data_file):
    return Auth(app, data_file)


# ── Routes ─────────────────────────────────────────────────────────────────────

def _blueprint():
    bp = Blueprint('auth', __name__)

    def render_login(error=None, username='', status=200):
        auth = _auth()
        return render_template(
            'login.html',
            error=error,
            username=username,
            next=_safe_next(request.values.get('next')),
            password_login=bool(auth.providers.enabled('password')),
            redirect_providers=auth.providers.enabled('redirect'),
            no_users=auth.users.count() == 0,
            checkin_url='/checkin' if any(r.rule == '/checkin' for r in current_app.url_map.iter_rules()) else None,
        ), status

    @bp.route('/login', methods=['GET', 'POST'])
    def login():
        auth = _auth()
        if not auth.enabled:
            return redirect('/')
        if request.method == 'GET':
            if current_user():
                return redirect(_safe_next(request.args.get('next')))
            return render_login()

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        wait = auth.locked_for(username)
        if wait:
            return render_login(f'Too many failed attempts. Try again in {wait} seconds.', username, 429)
        for provider in auth.providers.enabled('password'):
            user = provider.authenticate(username, password)
            if user:
                auth.sign_in(user, provider.id)
                return redirect(_safe_next(request.form.get('next')))
        auth.record_failure(username)
        return render_login('Wrong username or password.', username, 401)

    @bp.route('/logout', methods=['POST'])
    def logout():
        session.clear()
        return redirect(url_for('auth.login'))

    @bp.route('/api/auth/me')
    def me():
        auth = _auth()
        return jsonify({'enabled': auth.enabled, 'user': current_user()})

    @bp.route('/auth/<provider_id>/start')
    def start(provider_id):
        provider = _auth().providers.get(provider_id)
        if not provider or provider.kind != 'redirect':
            abort(404)
        state = secrets.token_urlsafe(24)
        session['auth_state'] = state
        session['auth_next'] = _safe_next(request.args.get('next'))
        callback = url_for('auth.callback', provider_id=provider_id, _external=True)
        return redirect(provider.start(callback, state))

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
            identity = provider.finish(request, url_for('auth.callback', provider_id=provider_id, _external=True))
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
    @click.password_option(help='Prompted for when left out.')
    def add_user(username, display_name, password):
        try:
            auth.users.add(username, password, display_name=display_name)
        except UserError as exc:
            fail(exc)
        click.echo(f'Added {username}.')

    @users.command('passwd')
    @click.argument('username')
    @click.password_option(help='Prompted for when left out.')
    def set_password(username, password):
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
            click.echo(f"{user['username']:<24} {user['display_name']}" + (f'  [{extra}]' if extra else ''))

    app.cli.add_command(users)
