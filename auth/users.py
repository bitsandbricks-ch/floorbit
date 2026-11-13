"""Local user accounts, kept in data.json under ``auth_users``.

data.json is the one file docker-compose already mounts, so accounts survive a
container rebuild without another volume. Passwords are stored as werkzeug
hashes (scrypt); the plain password never touches the disk.

Accounts can also be linked to outside identities (``identities``), which is
how an SSO or Discord login will map to a user here later.
"""
import json
import os
import re
import secrets
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

USERNAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$')
MIN_PASSWORD_LENGTH = 8

# Hash of a random password, checked when the username is unknown so a failed
# login takes the same time whether or not the account exists.
_DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(16))


class UserError(ValueError):
    pass


def validate_username(username):
    username = (username or '').strip()
    if not USERNAME_RE.match(username):
        raise UserError('Usernames are 1 to 32 letters, digits, dots, dashes or underscores.')
    return username


def validate_password(password):
    if len(password or '') < MIN_PASSWORD_LENGTH:
        raise UserError(f'Passwords need at least {MIN_PASSWORD_LENGTH} characters.')
    return password


class UserStore:
    KEY = 'auth_users'

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    # file IO -------------------------------------------------------------
    def _read(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, 'r') as f:
            return json.load(f)

    def _users(self):
        return dict(self._read().get(self.KEY) or {})

    def _write_users(self, users):
        data = self._read()
        data[self.KEY] = users
        # In place, not via rename: data.json is bind-mounted in docker-compose.
        with open(self.path, 'w') as f:
            json.dump(data, f, indent=2)

    # reads ---------------------------------------------------------------
    def count(self):
        return len(self._users())

    def get(self, username):
        if not username:
            return None
        user = self._users().get(username.lower())
        return dict(user) if user else None

    def list(self):
        return sorted((public(u) for u in self._users().values()), key=lambda u: u['username'].lower())

    def find_by_identity(self, provider, subject):
        for user in self._users().values():
            if (user.get('identities') or {}).get(provider) == str(subject):
                return dict(user)
        return None

    def verify(self, username, password):
        """The user if the password matches, else None."""
        user = self.get((username or '').strip())
        if not user or not user.get('password_hash'):
            check_password_hash(_DUMMY_HASH, password or '')
            return None
        if not check_password_hash(user['password_hash'], password or ''):
            return None
        return user

    # writes --------------------------------------------------------------
    def add(self, username, password=None, display_name=None, identities=None):
        username = validate_username(username)
        if password is not None:
            validate_password(password)
        with self._lock:
            users = self._users()
            if username.lower() in users:
                raise UserError(f'User {username} already exists.')
            users[username.lower()] = {
                'username': username,
                'display_name': (display_name or '').strip() or username,
                'password_hash': generate_password_hash(password) if password else None,
                'identities': {k: str(v) for k, v in (identities or {}).items()},
                'session_version': 1,
                'created_at': int(time.time()),
            }
            self._write_users(users)
            return dict(users[username.lower()])

    def set_password(self, username, password):
        validate_password(password)
        with self._lock:
            users = self._users()
            user = users.get((username or '').lower())
            if not user:
                raise UserError(f'No user called {username}.')
            user['password_hash'] = generate_password_hash(password)
            # Signs out every session of this user.
            user['session_version'] = int(user.get('session_version', 1)) + 1
            self._write_users(users)

    def link_identity(self, username, provider, subject):
        with self._lock:
            users = self._users()
            user = users.get((username or '').lower())
            if not user:
                raise UserError(f'No user called {username}.')
            user.setdefault('identities', {})[provider] = str(subject)
            self._write_users(users)

    def remove(self, username):
        with self._lock:
            users = self._users()
            if users.pop((username or '').lower(), None) is None:
                raise UserError(f'No user called {username}.')
            self._write_users(users)


def public(user):
    """A user record without secrets, for templates and the API."""
    return {
        'username': user['username'],
        'display_name': user.get('display_name') or user['username'],
        'has_password': bool(user.get('password_hash')),
        'identities': sorted((user.get('identities') or {}).keys()),
    }
