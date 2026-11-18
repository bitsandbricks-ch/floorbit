"""The plugin Marketplace (docs/marketplace.md), the same way Hubra and labdex have one.

Optional integrations live in repositories of their own (``bitsandbricks-ch/floorbit-plugin-*``).
Each release is one signed bundle (floorbit/plugins/bundles.py), the same file the local agents
take. ``bitsandbricks-ch/floorbit-plugins`` lists them in an ``index.json`` signed with its own key:

    {"name": ..., "generated": ..., "key_id": ..., "signature": ...,
     "plugins": [{"id": "lancache", "name": ..., "description": ..., "author": ..., "homepage": ...,
                  "versions": [{"version": "1.2.0", "file": "lancache-1.2.0.tar.gz", "sha256": ...,
                                "floorbit": ">=1.4", "agent_api": 1, "date": ..., "changes": ...,
                                "withdrawn": "why, when it was pulled"}]}]}

What may be trusted, and who decides:

- Only the official index, and only plugins signed with the keys built into this image
  (``floorbit/keys/index/``, ``floorbit/keys/plugins/``): trust ``official``. There are no other
  sources or keys to add.
- An admin installs, updates, rolls back and removes, nothing more. A stolen admin login can't add
  a key or a source, so it can't make Floorbit or an agent run code nobody signed.

Installed plugins sit in ``FLOORBIT_PLUGIN_DIR`` (``plugins/`` next to the data) as
``<id>/<version>/``, with the archive kept in ``.archives/`` for the agents. Which version each one
runs is a document (``marketplace.json``), so every instance of a Floorbit with a database ends up
with the same plugins (``sync``), downloading what it lacks.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

from .plugins import PluginError, bundles, clean_touches, compatible, plugin_icons

DEFAULT_URL = 'https://bitsandbricks-ch.github.io/floorbit-plugins/index.json'  # TODO: Mike: final domain?
URL_ENV = 'FLOORBIT_MARKETPLACE_URL'
DIR_ENV = 'FLOORBIT_PLUGIN_DIR'
INDEX_TTL = 600          # an index is asked again after ten minutes, or when an admin refreshes
SYNC_EVERY = 60          # how often an instance checks whether another one installed something
MAX_INDEX = 2 * 1024 * 1024
VERSION_RE = re.compile(r'^[0-9][0-9A-Za-z.+-]{0,39}\Z')


def _env(name, default=''):
    # Straight from the environment, never from the settings page: these decide what is trusted.
    return os.environ.get(name, default)


class MarketError(PluginError):
    """Shown to the admin as it is."""


# keys and sources -------------------------------------------------------------------------------
def official_keys():
    return bundles.pinned_keys()


def source():
    """``{url}`` of the official index (``FLOORBIT_MARKETPLACE_URL`` points at a mirror of it)."""
    return {'url': (_env(URL_ENV, '') or '').strip() or DEFAULT_URL}


_cache: dict = {}
_cache_lock = threading.Lock()
STALE_FOR = 24 * 3600    # while a source is away, its last good index is used this long
_stale: dict = {}        # url -> why the last read failed, while the cached copy is used
_newest: dict = {}       # url -> the newest ``generated`` seen: an older signed index is a replay


def fetch_index(source, force=False):
    """The index, verified with the index keys built in. Cached for INDEX_TTL."""
    import requests
    url = source['url']
    with _cache_lock:
        hit = _cache.get(url)
    if hit and not force and time.time() - hit[0] < INDEX_TTL:
        return hit[1]
    try:
        try:
            doc = json.loads(_get_capped(url, MAX_INDEX, 15))
        except MarketError:
            raise MarketError('the index is too large') from None
        except (requests.RequestException, ValueError) as exc:
            raise MarketError(f'could not read the index: {type(exc).__name__}') from None
        bundles.verify_index(doc, bundles.pinned_keys(bundles.INDEX_KEYS_DIR))
        generated = str(doc.get('generated') or '')
        if generated and generated < _newest.get(url, ''):
            # Signed, but older than one already seen: someone serving an old index keeps a pulled
            # version looking fine (a freeze or replay). Keep the newer one.
            raise MarketError(f'the index is older ({generated}) than one already seen ({_newest[url]})')
    except PluginError as exc:
        # The source is away or answered wrong: keep using its last good index for a while, so a
        # GitHub outage doesn't empty the Marketplace or stop a new pod from getting its plugins.
        if hit and time.time() - hit[0] < STALE_FOR:
            _stale[url] = f'{exc}; showing the copy from {time.strftime("%H:%M", time.localtime(hit[0]))}'
            return hit[1]
        raise
    _newest[url] = max(_newest.get(url, ''), str(doc.get('generated') or ''))
    _stale.pop(url, None)
    with _cache_lock:
        _cache[url] = (time.time(), doc)
    return doc


def _get_capped(url, limit, timeout):
    """The body of a GET, read in pieces and refused past ``limit`` bytes, so a source that
    answers with something huge can't fill this server's memory first."""
    import requests
    with requests.get(url, timeout=timeout, stream=True, allow_redirects=True) as res:
        res.raise_for_status()
        if int(res.headers.get('Content-Length') or 0) > limit:
            raise MarketError('the answer is too large')
        # ``timeout`` counts per read: a source that drips a byte now and then would hold this
        # worker for hours, so the whole answer gets a deadline too.
        deadline = time.monotonic() + timeout * 4
        chunks, size = [], 0
        for chunk in res.iter_content(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise MarketError('the answer is too large')
            if time.monotonic() > deadline:
                raise requests.Timeout('the answer took too long')
            chunks.append(chunk)
        return b''.join(chunks)


def _text(v, n):
    return str(v or '')[:n]


def _api(value):
    """The agent API a version needs, from an index: a bad value counts as a newer one than any agent
    knows, so the version is never sent to an agent that can't run it."""
    if value is None:
        return 1
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 1000 else 1000


def versions_of(entry):
    """The entry's versions, newest first, with only the fields Floorbit uses."""
    out, seen = [], set()
    listed = entry.get('versions')
    for v in listed if isinstance(listed, list) else []:   # one odd entry never takes the page down
        if not isinstance(v, dict) or not isinstance(v.get('version'), str) or not isinstance(v.get('file'), str):
            continue
        ver = v['version']
        file = v['file']
        if not VERSION_RE.match(ver) or ver in seen or not file:
            continue
        seen.add(ver)
        out.append({'version': ver, 'file': file, 'sha256': _text(v.get('sha256'), 64),
                    'floorbit': _text(v.get('floorbit'), 60), 'agent_api': _api(v.get('agent_api')),
                    'date': _text(v.get('date'), 30), 'changes': _text(v.get('changes'), 4000),
                    'withdrawn': _text(v.get('withdrawn'), 300), 'touches': clean_touches(v.get('touches'))})
    return sorted(out, key=lambda v: bundles.version_key(v['version']), reverse=True)


def _offers(force=False):
    """``({id: (source, entry)}, source status)``."""
    src, offers = source(), {}
    try:
        doc = fetch_index(src, force)
    except PluginError as exc:
        return offers, {'url': src['url'], 'name': '', 'generated': '', 'error': str(exc)}
    status = {'url': src['url'], 'name': _text(doc.get('name'), 80),
              'generated': _text(doc.get('generated'), 40), 'error': _stale.get(src['url'], '')}
    for entry in doc['plugins']:
        pid = str(entry.get('id', '')) if isinstance(entry, dict) else ''
        if bundles.ID_RE.match(pid) and pid not in offers:
            offers[pid] = (src, entry)
    return offers, status


# where installed plugins live -------------------------------------------------------------------
def plugin_dir():
    from . import store  # each tenant installs its own (docs/tenancy.md)
    return Path((_env(DIR_ENV, '') or '').strip() or store.tenant_path('plugins'))


def _state_path():
    from . import store
    return store.tenant_path('marketplace.json')


def installed():
    """``{id: {version, previous, trust, source, at, by}}``: what this Floorbit should run."""
    from . import store
    found = store.read_json(_state_path(), {})
    plugins = found.get('plugins') if isinstance(found, dict) else None
    return {k: v for k, v in (plugins or {}).items() if isinstance(v, dict) and bundles.ID_RE.match(k)}


def _save(plugins):
    from . import store
    store.write_json(_state_path(), {'plugins': plugins})


def _folder(pid, version):
    return plugin_dir() / pid / version


def _archive(pid, version):
    return plugin_dir() / '.archives' / f'{pid}-{version}.tar.gz'


def _download(src, entry, ver):
    """Fetch, check and unpack one version into its folder; the signature document."""
    from urllib.parse import urljoin

    import requests
    pid = str(entry['id'])
    from .agent_plugins import BUNDLE_NAME_RE
    if not BUNDLE_NAME_RE.match(f'{pid}-{ver["version"]}.tar.gz'):
        raise MarketError(f'{pid} {ver["version"]}: not a version Floorbit can install')
    url = urljoin(src['url'], ver['file'])
    if not url.startswith('https://'):
        raise MarketError(f'{pid}: the index points outside HTTPS')
    try:
        data = _get_capped(url, bundles.MAX_BUNDLE, 60)
    except requests.RequestException as exc:
        raise MarketError(f'could not download {pid} {ver["version"]}: {type(exc).__name__}') from None
    if not ver['sha256'] or bundles.sha256(data) != ver['sha256']:
        raise MarketError(f'{pid} {ver["version"]}: the download does not match the index')
    dest = _folder(pid, ver['version'])
    # Pods sharing one plugin folder may fetch the same version at once: each unpacks into its own.
    tmp = dest.with_name(f'.{ver["version"]}.{os.getpid()}.{threading.get_ident()}.part')
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        bundles.unpack(data, tmp)
        doc = bundles.verify(tmp, official_keys(), pid=pid, version=ver['version'])
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(dest, ignore_errors=True)
    try:
        tmp.rename(dest)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)
        if not dest.is_dir():
            raise MarketError(f'could not put {pid} {ver["version"]} in place') from None
        # Another pod put the same signed version there meanwhile; loading checks it again.
    archive = _archive(pid, ver['version'])
    archive.parent.mkdir(parents=True, exist_ok=True)
    part = archive.with_name(f'.{archive.name}.{os.getpid()}.{threading.get_ident()}.part')
    part.write_bytes(data)
    part.replace(archive)   # an agent fetching it never gets half a file
    return doc


def _check_folder(pid, version):
    """Check an unpacked version's signature again; MarketError if it fails. A plugin signed
    with a community key (Floorbit took those once) fails here and stays unloaded until removed."""
    folder = _folder(pid, version)
    if not folder.is_dir():
        raise MarketError(f'{pid} {version} is not on this server')
    bundles.verify(folder, official_keys(), pid=pid, version=version)


def _load(registry, pid, version):
    _check_folder(pid, version)
    # Checked before loading: adding it would replace (and then drop) the plugin it names instead.
    named = _manifest(pid, version).get('id')
    if named != pid:
        raise MarketError(f'the bundle for {pid} holds plugin {str(named)[:40]}')
    spec = registry.add(_folder(pid, version), 'official')
    if spec.error:
        raise MarketError(f'{pid} {version} does not load: {spec.error}')
    return spec


def _manifest(pid, version):
    """An unpacked version's plugin.yaml, or {} when it can't be read."""
    import yaml
    try:
        manifest = yaml.safe_load((_folder(pid, version) / 'plugin.yaml').read_text(encoding='utf-8')) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    return manifest if isinstance(manifest, dict) else {}


def _schema_of(pid, version):
    """The ``schema:`` an unpacked version declares (0 for none)."""
    schema = _manifest(pid, version).get('schema')
    return schema if isinstance(schema, int) and not isinstance(schema, bool) else 0


PART_KEEP = 600   # seconds: an unpack another pod is busy with, not a leftover of a crash


def _in_flight(path):
    try:
        return path.name.endswith('.part') and time.time() - path.stat().st_mtime < PART_KEEP
    except OSError:
        return False


def _prune(pid, keep):
    root = plugin_dir() / pid
    for sub in root.iterdir() if root.is_dir() else ():
        if sub.name not in keep and not _in_flight(sub):
            shutil.rmtree(sub, ignore_errors=True)
    for f in (plugin_dir() / '.archives').glob(f'{pid}-*.tar.gz'):
        if f.name not in {f'{pid}-{v}.tar.gz' for v in keep}:
            with contextlib.suppress(OSError):
                f.unlink()


_lock = threading.Lock()


# what an admin does -----------------------------------------------------------------------------
def catalog(registry, force=False):
    """Everything the index offers, merged with what is installed, for the Marketplace page."""
    offers, status = _offers(force)
    have = installed()
    plugins = []
    for pid in sorted(set(offers) | set(have)):
        src, entry = offers.get(pid, (None, {}))
        mine = have.get(pid)
        spec = registry.specs.get(pid)
        versions = []
        for v in versions_of(entry):
            ok, why = compatible(v['floorbit'], registry.version)
            versions.append({k: v[k] for k in ('version', 'date', 'changes', 'withdrawn', 'floorbit')}
                            | {'compatible': ok, 'why': why})
        best = next((v['version'] for v in versions if v['compatible'] and not v['withdrawn']), None)
        current = mine['version'] if mine else None
        # What the version it would install (or update to) may touch: shown before anyone installs it.
        wanted = best if not current or (best and bundles.newer(best, current)) else current
        touches = next((v['touches'] for v in versions_of(entry) if v['version'] == wanted), None)
        name = _text(entry.get('name'), 80) or (spec.name if spec else pid)
        # Only a name Floorbit draws itself; anything else in the index shows the default icon.
        icon = entry.get('icon') if entry.get('icon') in plugin_icons() else ''
        plugins.append({
            'id': pid, 'name': name, 'icon': icon, 'description': _text(entry.get('description'), 500),
            'author': _text(entry.get('author'), 80), 'homepage': _text(entry.get('homepage'), 200),
            'source': src['url'] if src else (mine or {}).get('source', ''),
            'builtin': bool(spec and spec.trust in ('builtin', 'development')),
            'installed': current, 'previous': (mine or {}).get('previous'),
            'error': spec.error if (spec and mine) else ('' if not mine else 'not loaded'),
            'enabled': bool(spec and mine and registry.enabled(spec)),
            'withdrawn': next((v['withdrawn'] for v in versions if v['version'] == current), '') if current else '',
            'update': best if current and best and bundles.newer(best, current) else None,
            'best': best, 'versions': versions, 'listed': src is not None, 'touches': touches,
        })
    return {'source': status, 'plugins': plugins}


def install(registry, pid, version=None, user=None):
    """Install ``version`` (the newest one that fits when None), or update to it. Keeps the
    version it replaces for ``rollback``."""
    from . import audit
    with _lock:
        spec = registry.specs.get(pid)
        if spec is not None and spec.trust in ('builtin', 'development'):
            raise MarketError(f'{spec.name} ships with this Floorbit')
        offers, _ = _offers()
        if pid not in offers:
            raise MarketError(f'the Marketplace does not offer {pid}')
        src, entry = offers[pid]
        entry = {**entry, 'id': pid}
        versions = versions_of(entry)
        if version is None:
            ver = next((v for v in versions if not v['withdrawn'] and compatible(v['floorbit'], registry.version)[0]),
                       None)
            if ver is None:
                raise MarketError(f'no version of {pid} works with this Floorbit')
        else:
            ver = next((v for v in versions if v['version'] == str(version)), None)
            if ver is None:
                raise MarketError(f'{pid} has no version {version}')
            if ver['withdrawn']:
                raise MarketError(f'{pid} {ver["version"]} was withdrawn: {ver["withdrawn"]}')
            ok, why = compatible(ver['floorbit'], registry.version)
            if not ok:
                raise MarketError(why)
        have = installed()
        before = have.get(pid)
        if before and before['version'] == ver['version']:
            raise MarketError(f'{pid} {ver["version"]} is already installed')
        _download(src, entry, ver)
        try:
            spec = _load(registry, pid, ver['version'])
            # Its data moves to the new schema here, before the update counts: when that fails, the
            # version that ran before is put back and keeps the data it knows.
            registry.ensure_schema(spec)
        except PluginError:
            if before:   # put back what ran
                with contextlib.suppress(PluginError):
                    _load(registry, pid, before['version'])
            else:
                registry.drop(pid)
            _prune(pid, {before['version']} if before else set())
            raise
        have[pid] = {'version': ver['version'], 'previous': before['version'] if before else None,
                     'trust': 'official', 'source': src['url'], 'at': int(time.time()), 'by': user}
        _save(have)
        _prune(pid, {ver['version'], *([before['version']] if before else [])})
    if before:
        audit.record('plugins', f"Updated plugin {pid} from {before['version']} to {ver['version']}", user, pid)
    else:
        audit.record('plugins', f"Installed plugin {pid} {ver['version']}", user, pid)
    _tell_agents()
    return have[pid]


def rollback(registry, pid, user=None):
    """Back to the version the last update replaced (that one becomes the one to go back to)."""
    from . import audit
    with _lock:
        have = installed()
        mine = have.get(pid)
        if not mine or not mine.get('previous'):
            raise MarketError(f'no earlier version of {pid} is kept')
        old, new = mine['previous'], mine['version']
        older = _schema_of(pid, old)
        if registry.schema_of(pid) > older:
            raise MarketError(f'{pid} {old} can\'t read the data {new} moved to schema {registry.schema_of(pid)}')
        try:
            _load(registry, pid, old)
        except PluginError:
            with contextlib.suppress(PluginError):
                _load(registry, pid, new)
            raise
        have[pid] = {**mine, 'version': old, 'previous': new, 'at': int(time.time()), 'by': user}
        _save(have)
    audit.record('plugins', f'Rolled back plugin {pid} from {new} to {old}', user, pid)
    _tell_agents()
    return have[pid]


def uninstall(registry, pid, user=None):
    from . import audit
    with _lock:
        have = installed()
        if pid not in have:
            raise MarketError(f'{pid} is not installed from the Marketplace')
        gone = have.pop(pid)
        _save(have)
        registry.drop(pid)
        _prune(pid, set())
        with contextlib.suppress(OSError):
            (plugin_dir() / pid).rmdir()
    audit.record('plugins', f"Removed plugin {pid} {gone['version']}", user, pid)
    _tell_agents()


def _tell_agents():
    from .agent_plugins import reload_agents
    with contextlib.suppress(Exception):   # they pull it within a minute anyway
        reload_agents()


# every instance runs what marketplace.json says ------------------------------------------------
def sync(registry):
    """Load what is installed, fetching versions this instance doesn't have yet. Never fails:
    a plugin that can't be had is left out and logged. Returns how many couldn't be loaded, so
    the background loop tries those again."""
    from . import database
    failed = 0
    try:
        have = installed()
    except database.DatabaseUnavailable:
        return 1
    with _lock:
        ours = [s.id for s in registry.specs.values() if s.trust not in ('builtin', 'development')]
        for pid in [p for p in ours if p not in have]:
            registry.drop(pid)
        offers = None
        for pid, mine in have.items():
            spec = registry.specs.get(pid)
            if spec is not None and spec.path.name == mine['version'] and not spec.error:
                continue
            try:
                if not _folder(pid, mine['version']).is_dir():
                    if offers is None:
                        offers, _ = _offers()
                    src, entry = offers[pid]
                    ver = next(v for v in versions_of({**entry, 'id': pid}) if v['version'] == mine['version'])
                    _download(src, {**entry, 'id': pid}, ver)
                _load(registry, pid, mine['version'])
            except (PluginError, KeyError, StopIteration, OSError) as exc:
                failed += 1
                registry.log(pid, f'could not load {pid} {mine["version"]}: {exc or type(exc).__name__}')
    return failed


def agent_bundles():
    """``{id: {version, file, sha256, agent_api}}`` of installed plugins, for the agents: they
    trust only the plugin keys built into their image, as Floorbit does."""
    out = {}
    try:
        have = installed()
    except Exception:  # noqa: BLE001  # the agents keep what they run while the database is away
        return out
    for pid, mine in have.items():
        if mine.get('trust') != 'official':
            continue
        archive = _archive(pid, mine['version'])
        sig = _folder(pid, mine['version']) / bundles.SIGFILE
        try:
            api = int(json.loads(sig.read_text(encoding='utf-8')).get('agent_api') or 1)
            out[pid] = {'version': mine['version'], 'file': archive.name,
                        'sha256': bundles.sha256(archive.read_bytes()), 'agent_api': api}
        except (OSError, ValueError, TypeError):
            continue
    return out


def archive_file(name):
    """The path of an installed version's archive, by file name, or None."""
    for pid, mine in installed().items():
        path = _archive(pid, mine['version'])
        if path.name == name and path.is_file():
            return path
    return None


def init_marketplace(app, registry, start_background=True):
    sync(registry)
    started = threading.Event()

    def loop():
        from . import store
        seen, retry, backoff = None, 0.0, SYNC_EVERY
        while True:
            time.sleep(SYNC_EVERY)
            try:
                now = store.stamp(_state_path())
            except Exception:  # noqa: BLE001  # the database being away is not this loop's problem
                continue
            # Again when something changed, and also when the last try left a plugin out (the
            # index or GitHub was away): every minute at first, then up to every half hour.
            if now != seen or (retry and time.monotonic() >= retry):
                seen = now
                try:
                    failed = sync(registry)
                except Exception as exc:  # noqa: BLE001  # the loop must keep running
                    print(f'[marketplace] sync failed: {type(exc).__name__}: {exc}')
                    failed = 1
                if failed:
                    retry, backoff = time.monotonic() + backoff, min(backoff * 2, 1800)
                else:
                    retry, backoff = 0.0, SYNC_EVERY

    @app.before_request
    def start_marketplace_once():
        if start_background and not started.is_set():
            started.set()
            threading.Thread(target=loop, daemon=True, name='marketplace-sync').start()
