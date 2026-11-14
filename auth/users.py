"""Local user accounts, kept in data.json under ``auth_users``.

data.json is the one file docker-compose already mounts, so accounts survive a
container rebuild without another volume. Passwords are stored as werkzeug
hashes (scrypt); the plain password never touches the disk.

Accounts can also be linked to outside identities (``identities``), which is
how a Discord (or later SSO) login maps to a user here.
"""
import json
import os
import re
import secrets
import threading
import time

from werkzeug.security import check_password_hash, generate_password_hash

from . import roles

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


def _role(role):
    try:
        return roles.validate(role)
    except roles.RoleError as exc:
        raise UserError(str(exc)) from None


class UserStore:
    KEY = 'auth_users'

    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()

    # file IO -------------------------------------------------------------
    def _read(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
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
    def add(self, username, password=None, display_name=None, identities=None, role=roles.DEFAULT_ROLE,
            created_by=None):
        username = validate_username(username)
        role = _role(role)
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
                'role': role,
                'session_version': 1,
                'created_at': int(time.time()),
            }
            if created_by:   # a login provider that made this account on first sign-in
                users[username.lower()]['created_by'] = created_by
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

    def update(self, username, role=None, display_name=None):
        """Change role and/or display name. Refuses to demote the last admin."""
        with self._lock:
            users = self._users()
            user = users.get((username or '').lower())
            if not user:
                raise UserError(f'No user called {username}.')
            if role is not None:
                role = _role(role)
                if _manager(user) and 'accounts.manage' not in roles.permissions_of(role) \
                        and _admin_count(users) <= 1:
                    raise UserError('This is the last admin. Make someone else admin first.')
                # Sessions read the record on every request, so this applies at once.
                user['role'] = role
            if display_name is not None:
                user['display_name'] = display_name.strip()[:64] or user['username']
            self._write_users(users)
            return dict(user)

    def link_identity(self, username, provider, subject):
        """Link an outside login to this account; an empty subject unlinks it."""
        subject = str(subject or '').strip()
        with self._lock:
            users = self._users()
            user = users.get((username or '').lower())
            if not user:
                raise UserError(f'No user called {username}.')
            if not subject:
                (user.get('identities') or {}).pop(provider, None)
            else:
                for other in users.values():
                    if other is not user and (other.get('identities') or {}).get(provider) == subject:
                        raise UserError(f'That {provider} login is already linked to {other["username"]}.')
                user.setdefault('identities', {})[provider] = subject
            self._write_users(users)

    def remove(self, username):
        with self._lock:
            users = self._users()
            user = users.get((username or '').lower())
            if not user:
                raise UserError(f'No user called {username}.')
            if _manager(user) and _admin_count(users) <= 1:
                raise UserError('This is the last admin. Make someone else admin first.')
            del users[(username or '').lower()]
            self._write_users(users)


def _manager(user):
    return roles.can(user, 'accounts.manage')


def _admin_count(users):
    """Accounts that can still manage accounts (so nobody locks everyone out)."""
    return sum(1 for u in users.values() if _manager(u))


def public(user):
    """A user record without secrets, for templates and the API."""
    return {
        'username': user['username'],
        'display_name': user.get('display_name') or user['username'],
        'role': roles.of(user),
        'role_label': roles.label(roles.of(user)),
        'permissions': sorted(roles.permissions_of(roles.of(user))),
        'teams': dict(user.get('teams') or {}),
        'has_password': bool(user.get('password_hash')),
        'identities': sorted((user.get('identities') or {}).keys()),
        'discord_id': (user.get('identities') or {}).get('discord', ''),
        'created_by': user.get('created_by'),
    }
