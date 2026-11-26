"""The Marketplace's tools (docs/marketplace.md), for the plugin repositories and floorbit-plugins.

    python scripts/marketplace.py sign <plugin folder> --key plugin-key.pem --version 1.2.0 --out dist
    python scripts/marketplace.py build-index plugins.yaml site --key index-key.pem
    python scripts/marketplace.py check https://bitsandbricks-ch.github.io/floorbit-plugins/index.json
    python scripts/marketplace.py check-applications games
    python scripts/marketplace.py build-applications games site --key index-key.pem

``sign`` packs one plugin as ``<id>-<version>.tar.gz``, signed with the plugin key (the release job
of each ``floorbit-plugin-*`` repository). ``build-index`` reads the GitHub releases of the
repositories ``plugins.yaml`` lists or discovers, checks every archive like a Floorbit would,
copies them next to ``index.json`` and signs that with the index key (floorbit-plugins' publish
workflow). ``check`` downloads a published index and everything it offers and checks them again.
``build-applications`` writes Floorbit's own rules file for the applications, ``applications.json``,
from floorbit-plugins' curated ``games/`` folder (one ``<id>.yaml`` per application, each with a
``source:``), checked as a Floorbit checks a rules file and signed with the index key (#1504); every
Floorbit fetches it as its last rule source. ``check-applications`` checks that folder without a key
and writes a summary for the pull request that adds to it (#1612).

Every command refuses a key that isn't the one built into Floorbit for its purpose
(``floorbit/keys/plugins/``, ``floorbit/keys/index/``), and a key used for both.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from floorbit.plugins import bundles  # noqa: E402
from floorbit.plugins.agent import AGENT_API  # noqa: E402

API = 'https://api.github.com'


def _private(path, purpose):
    """(PEM bytes, key id), refused unless it is the pinned key for ``purpose`` and only that."""
    from cryptography.hazmat.primitives import serialization
    pem = Path(path).read_bytes()
    kid = bundles.key_id(serialization.load_pem_private_key(pem, None).public_key())
    plugin, index = bundles.pinned_keys(), bundles.pinned_keys(bundles.INDEX_KEYS_DIR)
    want, other = (plugin, index) if purpose == 'plugins' else (index, plugin)
    if kid not in want:
        sys.exit(f'the key is {kid}, not the {purpose} key built into Floorbit ({", ".join(want) or "none"})')
    if kid in other:
        sys.exit(f'the key {kid} is pinned for plugins and for the index; a key has one purpose')
    return pem, kid


def _manifest(folder):
    import yaml
    return yaml.safe_load((Path(folder) / 'plugin.yaml').read_text(encoding='utf-8')) or {}


# sign ------------------------------------------------------------------------------------------
def sign_folder(folder, pem, version, out):
    """Sign a copy of ``folder`` as ``version`` and write ``<id>-<version>.tar.gz`` into ``out``."""
    manifest = _manifest(folder)
    pid = str(manifest.get('id') or '')
    if not bundles.ID_RE.match(pid):
        raise SystemExit(f'plugin.yaml: bad id {pid!r}')
    if str(manifest.get('version', '')) != str(version):
        raise SystemExit(f"plugin.yaml says version {manifest.get('version')!r}, the tag {version!r}")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / pid
        shutil.copytree(folder, work, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '.git', '.github', 'tests', '.pytest_cache', '.ruff_cache', 'FLOORBIT_REF'))
        bundles.sign(work, pem, str(version), AGENT_API)
        data = bundles.pack(work)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f'{pid}-{version}.tar.gz'
    path.write_bytes(data)
    return path


def cmd_sign(args):
    pem, kid = _private(args.key, 'plugins')
    path = sign_folder(args.folder, pem, args.version, args.out)
    print(f'signed {path.name} with {kid}, sha256 {bundles.sha256(path.read_bytes())}')


# build-index -----------------------------------------------------------------------------------
class GitHub:
    def __init__(self, token=None):
        import requests
        self.s = requests.Session()
        self.s.headers['Accept'] = 'application/vnd.github+json'
        if token:
            self.s.headers['Authorization'] = f'Bearer {token}'

    def _all(self, url):
        out = []
        while url:
            res = self.s.get(url, timeout=30)
            res.raise_for_status()
            out += res.json()
            url = res.links.get('next', {}).get('url')
        return out

    def repos(self, owner):
        return [r['full_name'] for r in self._all(f'{API}/orgs/{owner}/repos?per_page=100&type=public')
                if not r.get('archived') and not r.get('is_template')]

    def releases(self, repo):
        return [r for r in self._all(f'{API}/repos/{repo}/releases?per_page=100')
                if not r.get('draft') and not r.get('prerelease')]

    def download(self, asset):
        res = self.s.get(asset['url'], headers={'Accept': 'application/octet-stream'}, timeout=60)
        res.raise_for_status()
        return res.content


def _repositories(config, gh):
    listed = {p['repo']: p for p in config.get('plugins') or [] if isinstance(p, dict) and p.get('repo')}
    found = set(listed)
    for d in config.get('discover') or []:
        found |= {r for r in gh.repos(d['owner']) if r.split('/', 1)[1].startswith(d['prefix'])}
    return sorted(found), listed


def build_index(config, out, index_pem, gh, log=print):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    keys = bundles.pinned_keys()
    repos, listed = _repositories(config, gh)
    plugins = []
    for repo in repos:
        withdrawn = {str(k): str(v) for k, v in (listed.get(repo, {}).get('withdrawn') or {}).items()}
        entry, versions = None, []
        for rel in gh.releases(repo):
            version = str(rel.get('tag_name', '')).removeprefix('v')
            assets = {a['name']: a for a in rel.get('assets') or []}
            name = next((n for n in assets if n.endswith(f'-{version}.tar.gz')), None)
            if not name:
                log(f'skip {repo} {version}: no <id>-{version}.tar.gz')
                continue
            data = gh.download(assets[name])
            pid = name[:-len(f'-{version}.tar.gz')]
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    bundles.unpack(data, Path(tmp) / pid)
                    sig = bundles.verify(Path(tmp) / pid, keys, pid, version)
                except bundles.BundleError as exc:
                    log(f'REFUSED {repo} {version}: {exc}')
                    continue
                manifest = _manifest(Path(tmp) / pid)
            # Signed is not enough: a manifest Floorbit would refuse is never listed.
            from floorbit.plugins import touches, validate
            problem = validate(manifest) if isinstance(manifest, dict) else 'plugin.yaml must be a mapping'
            if problem:
                log(f'REFUSED {repo} {version}: plugin.yaml: {problem}')
                continue
            if entry is None or bundles.newer(version, entry['_v']):
                entry = {'id': pid, 'name': str(manifest.get('name') or pid)[:80],
                         **({'icon': manifest['icon']} if manifest.get('icon') else {}),
                         'description': str(manifest.get('description') or '')[:500],
                         'author': str(manifest.get('author') or '')[:80],
                         'homepage': str(manifest.get('homepage') or f'https://github.com/{repo}')[:200],
                         'repository': repo, '_v': version}
            (out / name).write_bytes(data)
            versions.append({'version': version, 'file': name, 'sha256': bundles.sha256(data),
                             'floorbit': str(manifest.get('floorbit') or ''), 'agent_api': int(sig['agent_api']),
                             'date': str(rel.get('published_at') or '')[:10],
                             'changes': str(rel.get('body') or '')[:4000], 'touches': touches(manifest),
                             **({'withdrawn': withdrawn[version]} if version in withdrawn else {})})
            log(f'ok   {repo} {version}')
        if entry is None:
            continue
        if any(v['id'] == entry['id'] for v in plugins):
            log(f'REFUSED {repo}: another repository already offers {entry["id"]}')
            continue
        entry.pop('_v')
        entry['versions'] = sorted(versions, key=lambda v: bundles.version_key(v['version']), reverse=True)
        plugins.append(entry)
    doc = {'name': str(config.get('name') or 'Floorbit Marketplace'),
           'description': str(config.get('description') or ''),
           'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'plugins': sorted(plugins, key=lambda p: p['id'])}
    doc = bundles.sign_index(doc, index_pem)
    (out / 'index.json').write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    return doc


def cmd_build_index(args):
    import yaml
    pem, kid = _private(args.key, 'index')
    config = yaml.safe_load(Path(args.config).read_text(encoding='utf-8')) or {}
    doc = build_index(config, args.out, pem, GitHub(os.environ.get('GITHUB_TOKEN')))
    print(f"index.json: {len(doc['plugins'])} plugins, signed with {kid}")


# check -----------------------------------------------------------------------------------------
def check(url, get, log=print):
    """Download the index and every version it lists, and check them as a Floorbit installing them would."""
    from urllib.parse import urljoin
    doc = json.loads(get(url))
    bundles.verify_index(doc, bundles.pinned_keys(bundles.INDEX_KEYS_DIR))
    keys, bad = bundles.pinned_keys(), 0
    for p in doc['plugins']:
        for v in p.get('versions') or []:
            try:
                data = get(urljoin(url, v['file']))
                if bundles.sha256(data) != v['sha256']:
                    raise bundles.BundleError('checksum differs from the index')
                with tempfile.TemporaryDirectory() as tmp:
                    bundles.unpack(data, Path(tmp) / p['id'])
                    bundles.verify(Path(tmp) / p['id'], keys, p['id'], v['version'])
                log(f"ok   {p['id']} {v['version']}")
            except (bundles.BundleError, OSError, KeyError) as exc:
                log(f"BAD  {p['id']} {v.get('version')}: {exc}")
                bad += 1
    return bad


def cmd_check(args):
    import requests

    def get(u):
        res = requests.get(u, timeout=60)
        res.raise_for_status()
        return res.content
    sys.exit(1 if check(args.url, get) else 0)


# build-applications ----------------------------------------------------------------------------
MAX_SOURCE = 300


def load_games(folder):
    """The applications in floorbit-plugins' ``games/``: one ``<id>.yaml`` each, named by its id and
    saying where its facts come from (``source:``, a link or a note), so that a pull request adding
    one adds one file and two of them never conflict."""
    import yaml
    entries = []
    for path in sorted(Path(folder).glob('*.y*ml')):
        where = f'{Path(folder).name}/{path.name}'
        try:
            entry = yaml.safe_load(path.read_text(encoding='utf-8'))
        except yaml.YAMLError as exc:
            raise SystemExit(f'{where}: not YAML ({exc.__class__.__name__})') from None
        if not isinstance(entry, dict):
            raise SystemExit(f'{where}: one application, with id, name, kind and its matches')
        if str(entry.get('id')) != path.stem:
            raise SystemExit(f'{where}: the file is named after its id ({entry.get("id")!r})')
        source = ' '.join(str(entry.get('source') or '').split())
        if not 1 <= len(source) <= MAX_SOURCE:
            raise SystemExit(f'{where}: say where it comes from in source: (a link or a note, '
                             f'up to {MAX_SOURCE} characters)')
        entries.append({k: v for k, v in entry.items() if k != 'source'})
    return entries


def check_games(entries):
    """``entries`` checked as a Floorbit checks a rules file, or SystemExit naming the bad one."""
    from floorbit import application_sources, applications
    try:
        return application_sources._from_json({'version': 1, 'applications': entries},
                                              {'id': 'floorbit', 'name': 'Floorbit list'}, applications)
    except application_sources.SourceError as exc:
        raise SystemExit(f'games: {exc.message}') from None


def review_games(apps):
    """What a pull request's reviewer should look at: (problems that stop it, notes, summary lines).
    A shared CDN or a service many games use would count for this application only, so it stops the
    build; a domain another application has already counts for both, which is a note."""
    from floorbit import applications
    sys.path.insert(0, str(ROOT / 'scripts'))
    from applications_import import SHARED_CDNS
    owners = {}
    for app in applications.builtin()['apps'].values():
        for site in app['sites']:
            owners.setdefault(site, []).append(app['id'])
    for app in apps:
        for site in app['sites']:
            owners.setdefault(site, []).append(app['id'])
    problems, notes, lines = [], [], []
    for app in apps:
        shared = sorted(set(app['sites']) & SHARED_CDNS)
        if shared:
            problems.append(f"{app['id']}: {', '.join(shared)} is shared by many vendors and counts for nobody")
        for site in app['sites']:
            others = sorted(set(owners[site]) - {app['id']})
            if others:
                notes.append(f"{app['id']}: {site} also counts for {', '.join(others)}")
        what = [f"{len(app[k])} {label}" for k, label in (('sites', 'domains'), ('ports', 'ports'),
                                                          ('cidr', 'address ranges'), ('depots', 'depots'))
                if app[k]]
        lines.append(f"- **{app['name']}** (`{app['id']}`, {app['kind']}, {app['category']}): "
                     f"{', '.join(what) or 'nothing to match'}")
    return problems, notes, lines


def build_applications(entries, out, index_pem):
    """Check the curated applications and write them, signed, to ``out/applications.json``."""
    apps = check_games(entries)
    problems, _notes, _lines = review_games(apps)
    if problems:
        raise SystemExit('games: ' + '; '.join(problems))
    doc = {'name': 'Floorbit applications', 'version': 1,
           'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'applications': apps}
    doc = bundles.sign_rules(doc, index_pem)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'applications.json').write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
    return doc


def cmd_build_applications(args):
    pem, kid = _private(args.key, 'index')
    doc = build_applications(load_games(args.games), args.out, pem)
    print(f"applications.json: {len(doc['applications'])} applications, signed with {kid}")


def cmd_check_applications(args):
    apps = check_games(load_games(args.games))
    problems, notes, lines = review_games(apps)
    text = [f'## Floorbit applications: {len(apps)}', '', *lines]
    if notes:
        text += ['', '### Domains that also count for another application', '', *(f'- {n}' for n in notes)]
    if problems:
        text += ['', '### Problems', '', *(f'- {p}' for p in problems)]
    print('\n'.join(text))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('\n'.join(text) + '\n')
    if problems:
        raise SystemExit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('sign')
    s.add_argument('folder')
    s.add_argument('--key', required=True)
    s.add_argument('--version', required=True)
    s.add_argument('--out', default='dist')
    b = sub.add_parser('build-index')
    b.add_argument('config')
    b.add_argument('out')
    b.add_argument('--key', required=True)
    c = sub.add_parser('check')
    c.add_argument('url')
    ca = sub.add_parser('check-applications')
    ca.add_argument('games')
    a = sub.add_parser('build-applications')
    a.add_argument('games')
    a.add_argument('out')
    a.add_argument('--key', required=True)
    args = p.parse_args()
    {'sign': cmd_sign, 'build-index': cmd_build_index, 'check': cmd_check,
     'build-applications': cmd_build_applications, 'check-applications': cmd_check_applications}[args.cmd](args)


if __name__ == '__main__':
    main()
