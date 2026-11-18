"""Stored SSH logins for switches, at the moment of use: port actions, commands, the terminal and
config backups. The logins are the inventory's credentials (floorbit/inventory_scope.py: on a
device, its tags, its group or the defaults), sealed with floorbit/vault.py; see docs/credentials.md.

- **Only at the moment of use.** ``ssh_login_for`` opens the password for one connection; the caller
  drops it when that connection is done, like a typed login. Each use is in the audit log.
- A typed login still wins over a stored one.
- The older Settings > Switch logins (by name pattern) became inventory credentials when the data
  was moved up (floorbit/upgrades.py): ``*`` the defaults, one name its device, a pattern a tag.
"""
from .store import load_data


class CredentialError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _device(switch, data):
    """The inventory device with this name (or short name), or None."""
    from . import inventory
    name = str(switch or '').lower()
    short = name.split('.')[0]
    return next((d for d in inventory.devices(data, include_hidden=True)
                 if d['name'].lower() in (name, short) or d['name'].lower().split('.')[0] == short), None)


def covers(switch):
    """Is a login stored for this switch, on it, its tags, its group or the defaults? (Without
    opening it.) A switch that isn't in the inventory has none."""
    from . import inventory_scope
    data = load_data()
    dev = _device(switch, data)
    return dev is not None and inventory_scope._credential_for(data, dev, 'ssh')[0] is not None


def _inventory_ssh(data):
    from . import inventory_scope
    return [c for c in inventory_scope._creds(data) if c['kind'] == 'ssh']


def has_default():
    return any(c['owner_type'] == 'defaults' for c in _inventory_ssh(load_data()))


def any_set():
    return bool(_inventory_ssh(load_data()))


def ssh_login_for(switch, user=None):
    """``{"username", "password", "ref"}`` for this switch, opened now, or None. Logged in the audit
    log. ``ref`` says which credential it was, for ``report_failed``."""
    from . import inventory_scope
    data = load_data()
    dev = _device(switch, data)
    if dev is None:
        return None
    try:
        opened = inventory_scope.login_for(data, dev, 'ssh', user)
    except inventory_scope.ScopeError as exc:
        raise CredentialError(str(exc), exc.status) from None
    if opened is None:
        return None
    return {'username': opened['username'], 'password': opened.get('secret') or '',
            'ref': {'device_id': dev['id'], 'credential_id': opened['id'], 'rev': opened['rev']}}


def report_failed(ref, message, plugin=''):
    """A stored login was refused: block it on the device until a tech clears it (inventory_scope)."""
    if not ref:
        return None
    from . import inventory_scope
    return inventory_scope.auth_failed(ref['device_id'], ref['credential_id'], ref['rev'], plugin, message)


def is_login_error(exc):
    return 'login' in str(exc).lower() or 'auth' in str(exc).lower()
