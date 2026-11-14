"""API tokens (issue #40). See docs/api.md.

A token lets a script or another tool use the API without a browser session. Each one carries a
role, like an account, and can be limited to reading. Only a hash is kept, so the token itself is
shown once, when it is made. Kept in the accounts file under ``api_tokens``.

A request sends ``Authorization: Bearer fbt_<id>_<secret>``. Tokens never reach accounts, roles,
teams or the tokens themselves, so a leaked one can't make itself a new one or an account.
"""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

from . import roles

KEY = 'api_tokens'
PREFIX = 'fbt_'
MAX_TOKENS = 50
MAX_DAYS = 365
NAME_RE = re.compile(r'^[^\x00-\x1f<>]{1,60}$')
TOKEN_RE = re.compile(r'^fbt_([0-9a-f]{8})_([A-Za-z0-9_-]{20,80})$')
TOUCH_EVERY = 60   # seconds between "last used" writes, so a busy script doesn't rewrite the file
# Never reachable with a token: a token can't widen its own access.
BLOCKED = ('/api/users', '/api/roles', '/api/teams', '/api/settings/api-tokens', '/api/settings/webhooks')

_lock = threading.Lock()
_path = None


class TokenError(ValueError):
    pass


def configure(path_getter):
    global _path
    _path = path_getter


def _read():
    path = _path() if _path else None
    if not path or not os.path.exists(path):
        return {}
    from floorbit.store import read_json  # late: floorbit imports auth while it loads
    return read_json(path, {})


def _write(data):
    from floorbit.store import write_json  # in place: data.json is bind-mounted
    write_json(_path(), data)


def _tokens(data):
    raw = data.get(KEY)
    return {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def summary(record, now=None):
    now = time.time() if now is None else now
    expires = record.get('expires_at')
    return {
        'id': record['id'], 'name': record.get('name'), 'role': roles.of(record),
        'role_label': roles.label(roles.of(record)), 'read_only': bool(record.get('read_only')),
        'created_at': record.get('created_at'), 'created_by': record.get('created_by'),
        'expires_at': expires, 'expired': bool(expires and expires <= now),
        'last_used_at': record.get('last_used_at'),
    }


def all_tokens():
    return sorted((summary(t) for t in _tokens(_read()).values()), key=lambda t: -(t['created_at'] or 0))


def create(name, role, read_only=False, expires_days=None, user=None, now=None):
    """Make a token. Returns (summary, the token): the token is never shown again."""
    now = time.time() if now is None else now
    name = str(name or '').strip()
    if not NAME_RE.match(name):
        raise TokenError('Give the token a name (up to 60 characters), like "Discord bot".')
    try:
        role = roles.validate(role)
    except roles.RoleError as exc:
        raise TokenError(str(exc)) from None
    if expires_days in (None, '', 0):
        expires_at = None
    else:
        try:
            days = int(expires_days)
        except (TypeError, ValueError):
            raise TokenError(f'Expiry is a number of days, 1 to {MAX_DAYS}, or none.') from None
        if not 1 <= days <= MAX_DAYS:
            raise TokenError(f'Expiry is a number of days, 1 to {MAX_DAYS}, or none.')
        expires_at = now + days * 86400
    with _lock:
        data = _read()
        tokens = _tokens(data)
        if len(tokens) >= MAX_TOKENS:
            raise TokenError(f'There are already {MAX_TOKENS} tokens. Revoke one you no longer use.')
        if any(t.get('name', '').lower() == name.lower() for t in tokens.values()):
            raise TokenError(f'A token named "{name}" already exists.')
        token_id = secrets.token_hex(4)
        while token_id in tokens:
            token_id = secrets.token_hex(4)
        token = f'{PREFIX}{token_id}_{secrets.token_urlsafe(32)}'
        record = {'id': token_id, 'name': name, 'role': role, 'read_only': bool(read_only),
                  'hash': _hash(token), 'created_at': now, 'created_by': user, 'expires_at': expires_at,
                  'last_used_at': None}
        tokens[token_id] = record
        data[KEY] = tokens
        _write(data)
    return summary(record, now), token


def revoke(token_id):
    with _lock:
        data = _read()
        tokens = _tokens(data)
        record = tokens.pop(str(token_id), None)
        if not record:
            raise TokenError('No such token.')
        data[KEY] = tokens
        _write(data)
    return summary(record)


def check(token, now=None):
    """The token's record when it is valid, else None. Notes when it was last used."""
    now = time.time() if now is None else now
    found = TOKEN_RE.match(token or '')
    if not found:
        return None
    record = _tokens(_read()).get(found.group(1))
    if not record or not hmac.compare_digest(record.get('hash') or '', _hash(token)):
        return None
    if record.get('expires_at') and record['expires_at'] <= now:
        return None
    if now - (record.get('last_used_at') or 0) > TOUCH_EVERY:
        with _lock:
            data = _read()
            tokens = _tokens(data)
            if found.group(1) in tokens:
                tokens[found.group(1)]['last_used_at'] = now
                data[KEY] = tokens
                _write(data)
    return record


def as_user(record):
    """What current_user() answers for a request made with this token."""
    role = roles.of(record)
    return {
        'username': f"token:{record.get('name')}", 'display_name': f"{record.get('name')} (API token)",
        'role': role, 'role_label': roles.label(role), 'permissions': sorted(roles.permissions_of(role)),
        'teams': {}, 'has_password': False, 'identities': [], 'discord_id': '', 'created_by': record.get('created_by'),
        'api_token': record['id'], 'read_only': bool(record.get('read_only')),
    }


def blocked(path):
    return any(path == p or path.startswith(p + '/') for p in BLOCKED)


def bearer(headers):
    """The token in an ``Authorization: Bearer`` header, else None.

    Other schemes are left alone: a reverse proxy in front of Floorbit may use Basic auth.
    """
    scheme, _, rest = (headers.get('Authorization') or '').strip().partition(' ')
    return rest.strip() if scheme.lower() == 'bearer' else None
