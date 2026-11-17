"""Secrets kept by Floorbit, encrypted (issue #474): switch logins and game servers' RCON passwords (#472).

- **AES-256-GCM** (``cryptography``, already here for paramiko). Each value has its own nonce and is
  bound to its slot (the slot's name is the associated data), so a value copied into another slot
  doesn't open.
- **The key is never in data.json or the database.** ``FLOORBIT_SECRET_KEY_FILE`` names a file with
  the key (32 random bytes, base64), for example a Kubernetes secret. Without it, Floorbit makes
  ``secret.key`` next to its data on first use (mode 0600): backups and exports of the data then
  hold nothing readable, but whoever has the whole state folder has the key too. docs/credentials.md.
- **Rotation.** A value names the key it was made with. ``FLOORBIT_SECRET_OLD_KEY_FILES`` (comma
  separated) still opens values made with older keys, and ``python -m floorbit.vault rotate``
  writes every value again with the current key.

Values are opened only at the moment of use; nothing here keeps them in clear.
"""
import base64
import hashlib
import os
import secrets
import sys
import threading

from integrations import config

PREFIX = 'v1'
_lock = threading.Lock()


class VaultError(RuntimeError):
    pass


def _read_key(path):
    try:
        with open(path, 'rb') as f:
            raw = base64.b64decode(f.read().strip(), validate=True)
    except (OSError, ValueError) as exc:
        raise VaultError(f'Cannot read the secret key in {path}: {exc}') from None
    if len(raw) != 32:
        raise VaultError(f'The secret key in {path} must be 32 bytes, base64 encoded.')
    return raw


def _key_id(key):
    return hashlib.sha256(key).hexdigest()[:8]


def default_key_file():
    from . import store  # a tenant's secrets are its own, under its own key
    return store.tenant_path('secret.key')


def current_key():
    """The key new values are made with: FLOORBIT_SECRET_KEY_FILE, or secret.key made on first use."""
    path = (config.get('FLOORBIT_SECRET_KEY_FILE') or '').strip()
    if path:
        return _read_key(path)
    path = default_key_file()
    with _lock:
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)   # a hosted tenant's folder may be new
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(base64.b64encode(secrets.token_bytes(32)) + b'\n')
            print(f'[vault] made a secret key in {path}; set FLOORBIT_SECRET_KEY_FILE to keep it elsewhere')
    return _read_key(path)


def _keys():
    keys = {}
    for path in filter(None, (p.strip() for p in (config.get('FLOORBIT_SECRET_OLD_KEY_FILES') or '').split(','))):
        key = _read_key(path)
        keys[_key_id(key)] = key
    key = current_key()
    keys[_key_id(key)] = key
    return keys


def _aesgcm(key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key)


def seal(slot, value):
    """``value`` (text) encrypted for ``slot``: ``v1:<key id>:<nonce>:<ciphertext>``."""
    key = current_key()
    nonce = secrets.token_bytes(12)
    sealed = _aesgcm(key).encrypt(nonce, str(value).encode('utf-8'), str(slot).encode('utf-8'))
    b64 = base64.urlsafe_b64encode
    return f'{PREFIX}:{_key_id(key)}:{b64(nonce).decode()}:{b64(sealed).decode()}'


def open_(slot, sealed):
    """The text sealed for ``slot``. VaultError when the key is missing or it was made for another slot."""
    from cryptography.exceptions import InvalidTag
    try:
        prefix, key_id, nonce, data = str(sealed).split(':')
    except ValueError:
        raise VaultError('A stored secret is damaged.') from None
    if prefix != PREFIX:
        raise VaultError('A stored secret is damaged.')
    key = _keys().get(key_id)
    if key is None:
        raise VaultError('A stored secret was made with a key Floorbit no longer has. Set it again.')
    try:
        clear = _aesgcm(key).decrypt(base64.urlsafe_b64decode(nonce), base64.urlsafe_b64decode(data),
                                     str(slot).encode('utf-8'))
    except (InvalidTag, ValueError):
        raise VaultError('A stored secret does not open with its key. Set it again.') from None
    return clear.decode('utf-8')


def needs_rotation(sealed):
    try:
        return str(sealed).split(':')[1] != _key_id(current_key())
    except IndexError:
        return False


def main(argv):
    if argv[1:] != ['rotate']:
        print('usage: python -m floorbit.vault rotate')
        return 2
    from . import credentials, game_servers
    done = credentials.rotate() + game_servers.rotate()
    print(f'Wrote {done} secret(s) again with the current key.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
