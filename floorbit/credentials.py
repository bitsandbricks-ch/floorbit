"""Switch logins kept by Floorbit (issue #474), so port actions, commands and the terminal work
without each tech typing one. Encrypted with floorbit/vault.py; see docs/credentials.md.

- **Write-only.** A login is set or replaced; the password never comes back out of the API. The
  username is shown, so the crew can tell which login is set.
- **Which switch.** A login is for every switch (``*``, the default), a name pattern (``sw-a-*``) or
  one switch. The most specific match wins: the exact name, then the longest pattern, then ``*``.
- **Only at the moment of use.** ``ssh_login_for`` opens the password for one connection; the caller
  drops it when that connection is done, like a typed login. Each use is in the audit log.
- Setting and removing need ``settings.manage``; using them needs what the action needs
  (``ports.act``). A typed login still wins over a stored one.
"""
import fnmatch
import re
import threading
import time
import uuid

from . import vault
from .store import load_data, save_data

KEY = 'credentials'
MAX = 100
# \Z, not $: $ also matches before a final newline, and the username goes to a switch.
SCOPE_RE = re.compile(r'^[A-Za-z0-9*?][A-Za-z0-9*?._-]{0,79}\Z')
USER_RE = re.compile(r'^[^\s\x00-\x1f]{1,64}\Z')
DEFAULT = '*'
_lock = threading.Lock()


class CredentialError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _slot(entry):
    return f"ssh:{entry['id']}"


def _all(data=None):
    data = load_data() if data is None else data
    return [c for c in data.get(KEY) or [] if c.get('kind') == 'ssh']


def listing():
    """What is set, without the passwords."""
    return [{'id': c['id'], 'kind': c['kind'], 'scope': c['scope'], 'username': c['username'],
             'set_at': c.get('set_at'), 'set_by': c.get('set_by')}
            for c in sorted(_all(), key=lambda c: (c['scope'] == DEFAULT, c['scope'].lower()))]


def set_ssh(body, by):
    """Set (or replace) the login for a scope. Returns the listing entry."""
    scope = str(body.get('scope') or DEFAULT).strip()
    if not SCOPE_RE.match(scope):
        raise CredentialError('A login is for * (every switch), a name pattern like sw-a-* or one switch name.')
    username, password = body.get('username'), body.get('password')
    if not isinstance(username, str) or not USER_RE.match(username):
        raise CredentialError('Type the switch username.')
    if not isinstance(password, str) or not password or len(password) > 256 or '\n' in password:
        raise CredentialError('Type the switch password (up to 256 characters, one line).')
    with _lock:
        data = load_data()
        rows = data.setdefault(KEY, [])
        entry = next((c for c in rows if c.get('kind') == 'ssh' and c['scope'].lower() == scope.lower()), None)
        if entry is None:
            if len(rows) >= MAX:
                raise CredentialError(f'Floorbit keeps at most {MAX} logins.')
            entry = {'id': uuid.uuid4().hex[:12], 'kind': 'ssh'}
            rows.append(entry)
        entry.update(scope=scope, username=username, set_at=time.time(), set_by=by)
        entry['password'] = vault.seal(_slot(entry), password)
        save_data(data)
    return next(c for c in listing() if c['id'] == entry['id'])


def delete(cred_id):
    with _lock:
        data = load_data()
        rows = data.get(KEY) or []
        gone = next((c for c in rows if c.get('id') == cred_id), None)
        if gone is None:
            return None
        data[KEY] = [c for c in rows if c is not gone]
        save_data(data)
    return {'scope': gone['scope'], 'username': gone['username']}


def _match(entries, switch):
    name = str(switch or '').lower()
    short = name.split('.')[0]
    exact = [c for c in entries if '*' not in c['scope'] and '?' not in c['scope']
             and c['scope'].lower() in (name, short)]
    if exact:
        return exact[0]
    patterns = [c for c in entries if c['scope'] != DEFAULT and ('*' in c['scope'] or '?' in c['scope'])
                and (fnmatch.fnmatchcase(name, c['scope'].lower()) or fnmatch.fnmatchcase(short, c['scope'].lower()))]
    if patterns:
        return max(patterns, key=lambda c: len(c['scope'].replace('*', '').replace('?', '')))
    return next((c for c in entries if c['scope'] == DEFAULT), None)


def _device(switch, data):
    """The inventory device with this name (or short name), or None."""
    from . import inventory
    name = str(switch or '').lower()
    short = name.split('.')[0]
    return next((d for d in inventory.devices(data, include_hidden=True)
                 if d['name'].lower() in (name, short) or d['name'].lower().split('.')[0] == short), None)


def covers(switch):
    """Is a login stored for this switch, on it, its tags or groups, or here? (Without opening it.)"""
    from . import inventory_scope
    data = load_data()
    dev = _device(switch, data)
    if dev is not None:
        return inventory_scope._credential_for(data, dev, 'ssh')[0] is not None
    return _match(_all(data), switch) is not None


def _inventory_ssh(data):
    from . import inventory_scope
    return [c for c in inventory_scope._creds(data) if c['kind'] == 'ssh']


def has_default():
    data = load_data()
    return any(c['scope'] == DEFAULT for c in _all(data)) or any(c['owner_type'] == 'defaults'
                                                                  for c in _inventory_ssh(data))


def any_set():
    data = load_data()
    return bool(_all(data)) or bool(_inventory_ssh(data))


def ssh_login_for(switch, user=None):
    """``{"username", "password", "ref"}`` for this switch, opened now, or None. Logged in the audit
    log. The inventory's credentials (device, tags, groups, defaults) come first, then the logins
    here by name pattern. ``ref`` says which one it was, for ``report_failed``."""
    from . import audit, inventory_scope
    data = load_data()
    dev = _device(switch, data)
    if dev is not None:
        try:
            opened = inventory_scope.login_for(data, dev, 'ssh', user)
        except inventory_scope.ScopeError as exc:
            raise CredentialError(str(exc), exc.status) from None
        if opened is None:
            return None
        return {'username': opened['username'], 'password': opened.get('secret') or '',
                'ref': {'device_id': dev['id'], 'credential_id': opened['id'], 'rev': opened['rev']}}
    entry = _match(_all(data), switch)
    if entry is None:
        return None
    try:
        password = vault.open_(_slot(entry), entry['password'])
    except vault.VaultError as exc:
        audit.record('credentials', f'Stored login for {entry["scope"]} did not open', user=user, target=switch,
                     ok=False)
        raise CredentialError(str(exc), 500) from None
    audit.record('credentials', f'Used the stored login for {entry["scope"]}', user=user, target=switch)
    return {'username': entry['username'], 'password': password}


def report_failed(ref, message, plugin=''):
    """A stored login was refused: block it on the device until a tech clears it (inventory_scope)."""
    if not ref:
        return None
    from . import inventory_scope
    return inventory_scope.auth_failed(ref['device_id'], ref['credential_id'], ref['rev'], plugin, message)


def is_login_error(exc):
    return 'login' in str(exc).lower() or 'auth' in str(exc).lower()


def rotate():
    """Write every stored password again with the current key. Returns how many."""
    with _lock:
        data = load_data()
        done = 0
        for entry in data.get(KEY) or []:
            if entry.get('password') and vault.needs_rotation(entry['password']):
                entry['password'] = vault.seal(_slot(entry), vault.open_(_slot(entry), entry['password']))
                done += 1
        if done:
            save_data(data)
    return done
