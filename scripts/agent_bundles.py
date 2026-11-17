"""Signed plugin bundles for the local agents (floorbit/plugins/bundles.py).

    python scripts/agent_bundles.py keygen                       # new key pair: key.pem, floorbit.pub
    python scripts/agent_bundles.py build --key key.pem --out agent-bundles
    python scripts/agent_bundles.py verify agent-bundles

``build`` signs every built-in plugin (but demo) with the release's VERSION and writes
``<id>-<version>.tar.gz`` and ``index.json`` to ``--out``. It refuses a key the agents don't pin.
"""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from floorbit.plugins import bundles  # noqa: E402
from floorbit.plugins.agent import AGENT_API  # noqa: E402

SKIP = {'demo'}


def keygen(args):
    pem, pub = bundles.keygen()
    key, pubfile = Path(args.key), Path(args.pub)
    key.touch(mode=0o600)
    key.write_bytes(pem)
    pubfile.write_text(pub)
    print(f'{key} (private: into the plugin-signing environment, nowhere else), {pubfile} '
          f'(public: into floorbit/keys/agent-plugins/), key id {bundles.key_id(bundles.load_public(pub))}')


def build(args):
    from cryptography.hazmat.primitives import serialization
    pem = Path(args.key).read_bytes()
    kid = bundles.key_id(serialization.load_pem_private_key(pem, None).public_key())
    pinned = bundles.pinned_keys(args.keys)
    if kid not in pinned:
        sys.exit(f'the key {kid} is not one the agents pin ({", ".join(pinned) or "none"}): add its .pub first')
    version = args.version or (ROOT / 'VERSION').read_text().strip()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    index = {'version': version, 'agent_api': AGENT_API, 'plugins': {}}
    src = ROOT / 'floorbit' / 'builtin_plugins'
    for folder in sorted(p for p in src.iterdir() if p.is_dir() and (p / 'plugin.yaml').is_file()):
        if folder.name in SKIP or folder.name.startswith(('_', '.')):
            continue
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / folder.name
            shutil.copytree(folder, work, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            doc = bundles.sign(work, pem, version, AGENT_API)
            data = bundles.pack(work)
        name = f"{doc['id']}-{version}.tar.gz"
        (out / name).write_bytes(data)
        index['plugins'][doc['id']] = {'version': version, 'file': name, 'sha256': bundles.sha256(data),
                                       'agent_api': AGENT_API}
        print(f'signed {name}')
    (out / 'index.json').write_text(json.dumps(index, indent=2, sort_keys=True) + '\n')


def verify(args):
    keys = bundles.pinned_keys(args.keys)
    folder = Path(args.folder)
    index = json.loads((folder / 'index.json').read_text())
    bad = 0
    for pid, entry in sorted(index['plugins'].items()):
        data = (folder / entry['file']).read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                if bundles.sha256(data) != entry['sha256']:
                    raise bundles.BundleError('checksum differs from index.json')
                bundles.unpack(data, Path(tmp) / pid)
                bundles.verify(Path(tmp) / pid, keys, pid, entry['version'])
                print(f'ok   {entry["file"]}')
            except bundles.BundleError as exc:
                print(f'BAD  {entry["file"]}: {exc}')
                bad += 1
    sys.exit(1 if bad else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    k = sub.add_parser('keygen')
    k.add_argument('--key', default='key.pem')
    k.add_argument('--pub', default='floorbit.pub')
    b = sub.add_parser('build')
    b.add_argument('--key', required=True)
    b.add_argument('--out', default='agent-bundles')
    b.add_argument('--version')
    b.add_argument('--keys', help='folder of pinned public keys (default: floorbit/keys/agent-plugins)')
    v = sub.add_parser('verify')
    v.add_argument('folder')
    v.add_argument('--keys')
    args = p.parse_args()
    {'keygen': keygen, 'build': build, 'verify': verify}[args.cmd](args)


if __name__ == '__main__':
    main()
