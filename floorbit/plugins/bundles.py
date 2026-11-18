"""Signed plugin bundles for the local agents (docs/agent-plugins.md, "Updates").

A bundle is one built-in plugin's folder, packed as a .tar.gz, with SIGNATURE.json next to
plugin.yaml:

    {"id": "lancache", "version": "0.5.0", "agent_api": 1, "files": {"plugin.yaml": "<sha256>", ...},
     "key_id": "3f9a...", "signature": "<base64 Ed25519 over the canonical JSON of id, version,
     agent_api and files>"}

The release workflow signs them with a key that only its signing job sees; the hosted Floorbit
merely hands them on. An agent installs one only when it verifies against a public key built into
its image (floorbit/keys/plugins/), is newer than what it runs, and needs no newer agent. So a
stolen hosted login can at most offer a bundle Floorbit's release already signed.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path

from .base import PluginError

SIGFILE = 'SIGNATURE.json'
INDEX = 'index.json'
KEYS_DIR = Path(__file__).resolve().parent.parent / 'keys' / 'plugins'
SKIP = {'__pycache__', '.git', '.pytest_cache'}
MAX_BUNDLE = 8 * 1024 * 1024     # packed; a plugin is a few files of Python and YAML
MAX_FILES = 200
ID_RE = re.compile(r'^[a-z][a-z0-9-]{0,39}\Z')
# A plugin never brings code for the browser (its screens are data Floorbit draws) or native code
# (docs/plugin-spec.md, "The files in a bundle"): refused when it is signed and when it is checked.
REFUSED_SUFFIXES = frozenset({'.js', '.mjs', '.cjs', '.css', '.html', '.htm', '.wasm', '.so', '.pyd', '.dll',
                              '.dylib', '.whl', '.egg', '.exe'})
REFUSED_DIRS = frozenset({'static', 'templates'})


class BundleError(PluginError):
    """A bundle that must not be installed."""


def version_key(text):
    return tuple(int(p) for p in re.findall(r'\d+', str(text))[:3]) or (0,)


def newer(a, b):
    """True when version ``a`` is newer than ``b`` (missing parts count as 0)."""
    x, y = version_key(a), version_key(b)
    n = max(len(x), len(y))
    return x + (0,) * (n - len(x)) > y + (0,) * (n - len(y))


# keys ------------------------------------------------------------------------------------------
def _crypto():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    return serialization, Ed25519PrivateKey, Ed25519PublicKey


def key_id(pub) -> str:
    serialization, _, _ = _crypto()
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]


def load_public(text: str):
    serialization, _, pub_cls = _crypto()
    text = text.strip()
    if text.startswith('-----BEGIN'):
        key = serialization.load_pem_public_key(text.encode())
    else:   # bare base64 of the 32 raw bytes
        key = pub_cls.from_public_bytes(base64.b64decode(text))
    if not isinstance(key, pub_cls):
        raise ValueError('not an Ed25519 public key')
    return key


def pinned_keys(keys_dir=None) -> dict:
    """{key id: public key} built into this image. Empty: no bundle is ever installed."""
    out = {}
    folder = Path(keys_dir or KEYS_DIR)
    if folder.is_dir():
        for f in sorted(folder.glob('*.pub')):
            try:
                k = load_public(f.read_text())
            except (ValueError, TypeError):
                continue
            out[key_id(k)] = k
    return out


def keygen() -> tuple[bytes, str]:
    """(private PEM, public PEM) for a new signing key."""
    serialization, priv_cls, _ = _crypto()
    key = priv_cls.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return pem, pub


# signing ---------------------------------------------------------------------------------------
def file_hashes(root: Path) -> dict:
    out = {}
    for p in sorted(Path(root).rglob('*')):
        rel = p.relative_to(root)
        if any(part in SKIP for part in rel.parts) or rel.suffix == '.pyc' or rel.as_posix() == SIGFILE:
            continue
        if p.is_symlink():
            raise BundleError(f'symlinks are not allowed in a bundle ({rel})')
        if p.is_file() and (rel.suffix.lower() in REFUSED_SUFFIXES or rel.parts[0] in REFUSED_DIRS):
            raise BundleError(f'a plugin can\'t ship {rel}: no browser or native code (docs/plugin-spec.md)')
        if p.is_file():
            out[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _payload(pid, version, agent_api, files) -> bytes:
    return json.dumps({'id': pid, 'version': version, 'agent_api': agent_api, 'files': files},
                      sort_keys=True, separators=(',', ':')).encode()


def sign(root: Path, private_pem: bytes, version: str, agent_api: int) -> dict:
    """Write SIGNATURE.json into the plugin folder ``root``."""
    import yaml
    serialization, priv_cls, _ = _crypto()
    key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(key, priv_cls):
        raise ValueError('not an Ed25519 private key')
    manifest = yaml.safe_load((Path(root) / 'plugin.yaml').read_text(encoding='utf-8')) or {}
    pid = str(manifest.get('id') or Path(root).name)
    files = file_hashes(root)
    doc = {'id': pid, 'version': str(version), 'agent_api': int(agent_api), 'files': files,
           'key_id': key_id(key.public_key())}
    doc['signature'] = base64.b64encode(key.sign(_payload(pid, doc['version'], doc['agent_api'], files))).decode()
    (Path(root) / SIGFILE).write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    return doc


def verify(root: Path, keys: dict, pid=None, version=None) -> dict:
    """The signature document when ``root`` is exactly what a pinned key signed; else BundleError."""
    from cryptography.exceptions import InvalidSignature
    sigfile = Path(root) / SIGFILE
    if not sigfile.is_file():
        raise BundleError('not signed')
    try:
        doc = json.loads(sigfile.read_text(encoding='utf-8'))
        kid = str(doc['key_id'])
        signed = (str(doc['id']), str(doc['version']), int(doc['agent_api']), dict(doc['files']))
    except (ValueError, KeyError, TypeError) as exc:
        raise BundleError(f'unreadable signature: {exc}') from None
    pub = keys.get(kid)
    if pub is None:
        raise BundleError(f'signed with key {kid}, which this agent does not trust')
    if file_hashes(root) != signed[3]:
        raise BundleError('the files differ from what was signed')
    try:
        pub.verify(base64.b64decode(doc['signature']), _payload(*signed))
    except (InvalidSignature, ValueError, TypeError):
        raise BundleError('bad signature') from None
    if pid is not None and signed[0] != pid:
        raise BundleError(f'signed for {signed[0]}, not {pid}')
    if version is not None and signed[1] != str(version):
        raise BundleError(f'signed as version {signed[1]}, not {version}')
    return doc


# packing ---------------------------------------------------------------------------------------
def pack(root: Path) -> bytes:
    """The folder as a .tar.gz with fixed times and owners, so the same folder packs the same."""
    buf = io.BytesIO()
    names = [*sorted(file_hashes(root)), SIGFILE]
    with tarfile.open(fileobj=buf, mode='w:gz', format=tarfile.PAX_FORMAT) as tar:
        for name in names:
            data = (Path(root) / name).read_bytes()
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def unpack(data: bytes, dest: Path) -> None:
    """Regular files only, inside ``dest``; anything else refuses the whole bundle."""
    if len(data) > MAX_BUNDLE:
        raise BundleError('bundle too large')
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
            members = tar.getmembers()
            if len(members) > MAX_FILES:
                raise BundleError('too many files in the bundle')
            total = 0
            for m in members:
                parts = Path(m.name).parts
                if not m.isfile() or Path(m.name).is_absolute() or '..' in parts or not parts:
                    raise BundleError(f'refused entry in the bundle: {m.name}')
                total += m.size
                if total > 4 * MAX_BUNDLE:
                    raise BundleError('bundle too large')
                target = dest.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(m).read())
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise BundleError(f'unreadable bundle: {exc}') from None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# the Marketplace's index -------------------------------------------------------------------------
INDEX_KEYS_DIR = KEYS_DIR.parent / 'index'
INDEX_FIELDS = ('name', 'description', 'generated', 'key_id', 'plugins')


def _index_payload(doc: dict) -> bytes:
    return json.dumps({k: doc.get(k) for k in INDEX_FIELDS}, sort_keys=True, separators=(',', ':')).encode()


def sign_index(doc: dict, private_pem: bytes) -> dict:
    """Add key_id and signature to a Marketplace index (floorbit-plugins' publish workflow)."""
    serialization, priv_cls, _ = _crypto()
    key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(key, priv_cls):
        raise ValueError('not an Ed25519 private key')
    doc = {**doc, 'key_id': key_id(key.public_key())}
    doc['signature'] = base64.b64encode(key.sign(_index_payload(doc))).decode()
    return doc


def verify_index(doc, keys: dict) -> dict:
    """The index when one of ``keys`` signed it; else BundleError."""
    from cryptography.exceptions import InvalidSignature
    if not isinstance(doc, dict) or not doc.get('signature') or not isinstance(doc.get('plugins'), list):
        raise BundleError('the index is not signed')
    pub = keys.get(str(doc.get('key_id')))
    if pub is None:
        raise BundleError(f"the index is signed with key {doc.get('key_id')}, which this Floorbit does not trust")
    try:
        pub.verify(base64.b64decode(doc['signature']), _index_payload(doc))
    except (InvalidSignature, ValueError, TypeError):
        raise BundleError('bad index signature') from None
    return doc
