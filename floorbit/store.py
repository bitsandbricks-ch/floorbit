"""The floor plan's data file (inventory, seat blocks, settings, accounts).

Everything lives in one JSON file, ``DATA_FILE``, read and written whole.

It is written in place, not swapped in by a rename, because older compose files bind-mount the single
file and a rename onto a bind mount fails. So a reader can catch it between the truncate and the
write. ``read_json`` and ``write_json`` close that gap: inside one process a lock keeps them apart,
and a reader in another process (more than one worker) that finds half a file waits and reads again.
Every reader and writer of data.json (here, auth/ and the settings store) goes through them.

A write that dies halfway (a full disk, the pod killed) would leave half a file, and Floorbit would
not start again. So each document is first written whole to ``<file>.next`` beside it: if that
fails, the file itself is never touched; if the write in place fails, ``.next`` holds the complete
document and a read that finds the file broken takes it from there.

Many parts of Floorbit (requests, background monitors) load the whole document, change their own
part and save it whole. ``write_json`` keeps the top-level parts a saver did not change as they are
now, so one saving a copy it loaded a moment ago doesn't undo what another saved in between.
"""
import contextvars
import json
import os
import re
import shutil
import threading
import time
from contextlib import contextmanager

# Compose keeps it in the state folder with everything else (docs/install.md).
DATA_FILE = os.environ.get('FLOORBIT_DATA_FILE') or 'data.json'
NEXT = '.next'           # the last complete write, beside the file (see above)
READ_TRIES = 6            # about 0.3 s in all before a half-written file counts as broken

_lock = threading.RLock()
_warned = set()


class Doc(dict):
    """A document as ``read_json`` found it. It remembers that text, so ``write_json`` can tell
    which parts the caller changed and keep what was written in the meantime (see ``_merge``)."""
    _base = None      # (path, the text the caller's copy came from)
    _tenant = None    # the tenant's parts as loaded, in a later event (see load_data)
    _upgraded = False  # load_data moved it to the current shape (floorbit/upgrades.py)


def _doc(found, path, text):
    if not isinstance(found, dict):
        return found
    doc = Doc(found)
    doc._base = (path, text)
    return doc


_GONE = object()     # a key or an item that isn't there, in _merge3
WRITE_TRIES = 8      # a save that keeps meeting another pod's write merges again this often


def _by_id(value):
    """``{id: item}`` for a list of objects that each carry a distinct ``id``, else None."""
    if not isinstance(value, list):
        return None
    out = {}
    for item in value:
        key = item.get('id') if isinstance(item, dict) else None
        if not isinstance(key, (str, int)) or isinstance(key, bool) or key in out:
            return None
        out[key] = item
    return out


def _merge3(base, current, mine):
    """``mine`` laid over ``current``, both changed from ``base``. Objects merge key by key and lists of
    objects with ids item by item, so two people adding a team or a seat block at the same moment both
    keep theirs. Where both changed the same value, ``mine`` (the later save) wins, as before."""
    if mine == base:
        return current
    if current in (base, mine):
        return mine
    if base is _GONE and type(current) is type(mine) and isinstance(mine, (dict, list)):
        base = type(mine)()     # both added it (the first team, the first seat block): keep both
    if isinstance(base, dict) and isinstance(current, dict) and isinstance(mine, dict):
        out = {}
        for key in [*current, *(k for k in mine if k not in current)]:
            value = _merge3(base.get(key, _GONE), current.get(key, _GONE), mine.get(key, _GONE))
            if value is not _GONE:
                out[key] = value
        return out
    b, c, m = _by_id(base), _by_id(current), _by_id(mine)
    if b is not None and c is not None and m is not None:
        out = []
        for key in [*c, *(k for k in m if k not in c)]:
            value = _merge3(b.get(key, _GONE), c.get(key, _GONE), m.get(key, _GONE))
            if value is not _GONE:
                out.append(value)
        return out
    return mine


def _merge(data, base_text, current_text):
    """What to write: ``data`` with what others saved since the caller loaded it kept. Background tasks,
    requests and other pods each load the whole document, change their part and save it whole:
    without this, one saving a copy it loaded a moment earlier puts back everything another changed
    meanwhile (an incident marked fixed came back open; with two pods, a third of the teams and seat
    blocks added at the same moment were lost)."""
    if current_text is None or current_text == base_text:
        return data     # nobody wrote in between: the usual case, no parsing
    try:
        base, current = json.loads(base_text), json.loads(current_text)
    except (TypeError, ValueError):
        return data
    if not isinstance(base, dict) or not isinstance(current, dict):
        return data
    return _merge3(base, current, json.loads(json.dumps(data)))


def read_json(path, default=None):
    """The document's JSON, or ``default`` when it doesn't exist. From the database when
    FLOORBIT_DATABASE_URL names one (floorbit/database.py), else from the file. A caller whose
    default is an object (``{}``) always gets an object back."""
    found = _read_json(path, default)
    if isinstance(default, dict) and not isinstance(found, dict):
        last = _last_object(path)
        _not_an_object(path, found, last is not None)
        return default if last is None else last
    return found


def _last_object(path):
    """The last complete write beside a file that holds JSON of the wrong shape (a list, a number),
    so the accounts and the plan in it aren't replaced by an empty document. Files only."""
    from . import database
    if database.backend().kind != 'files':
        return None
    try:
        with open(path + NEXT) as f:
            text = f.read()
        last = json.loads(text)
    except (OSError, ValueError):
        return None
    return _doc(last, path, text) if isinstance(last, dict) else None


def _not_an_object(path, found, recovered):
    if path in _warned:
        return
    _warned.add(path)
    # The next save writes over it: keep what someone put there, they may want it back.
    kept = path + '.wrong-shape'
    try:
        if os.path.isfile(path) and not os.path.exists(kept):
            shutil.copyfile(path, kept)
    except OSError:
        pass
    then = f'using the last complete copy, {path}{NEXT}' if recovered else 'starting from empty until the next save'
    print(f'[store] {path} holds {type(found).__name__}, not an object (edited by hand?); {then}. '
          f'Its content is kept in {kept}.')


def _read_json(path, default):
    from . import database
    db = database.backend()
    if db.kind != 'files':
        key = database.key_for(path, db.root)
        text = db.get_text(key)
        if text is not database._MISSING:
            return _doc(json.loads(text), path, text)
        # Not in the database yet: take the file's content over, once (docs/database.md).
        found = _read_file(path, database._MISSING)
        if found is database._MISSING:
            return default
        text = json.dumps(found[0])
        with _lock:
            if db.get(key) is database._MISSING:
                db.put(key, text)
        return _doc(found[0], path, text)
    found = _read_file(path, None)
    return default if found is None else _doc(found[0], path, found[1])


def _read_file(path, default):
    """(document, its text), or ``default`` when there is no file."""
    for attempt in range(READ_TRIES):
        try:
            with _lock, open(path) as f:
                text = f.read()
            return json.loads(text), text
        except FileNotFoundError:
            return default
        except json.JSONDecodeError:
            if attempt == READ_TRIES - 1:
                return _read_next(path)
            time.sleep(0.02 * (attempt + 1))   # another process is writing it right now
    return default


def _read_next(path):
    """The last complete write, when the file itself is broken; raises when that is broken too."""
    try:
        with open(path + NEXT) as f:
            text = f.read()
        found = json.loads(text)
    except (OSError, json.JSONDecodeError):
        with open(path) as f:
            return json.load(f), None   # nothing to fall back on: the file's own error
    if path not in _warned:     # once: every request reads it until the next save mends it
        _warned.add(path)
        print(f'[store] {path} is broken (a write cut short?); using the last complete copy, {path}{NEXT}')
    return found, text


def _current_text(path):
    """The file's text as it is now, or None when it is missing or half-written."""
    try:
        with open(path) as f:
            text = f.read()
        json.loads(text)
        return text
    except (OSError, ValueError):
        return None


def write_json(path, data):
    # Serialised first and written in one go, so the file is empty or half-written for as short
    # a time as possible; a failure to serialise leaves the old file untouched.
    from . import database
    db = database.backend()
    base = getattr(data, '_base', None)
    base_text = base[1] if base and base[0] == path else None
    with _lock:
        if db.kind != 'files':
            key = database.key_for(path, db.root)
            if base_text is None:
                out = data
                text = json.dumps(out)
                db.put(key, text)
            else:
                # Other pods write the same document: merge with what is there now and store it only
                # if nobody wrote in between, else merge again (compare and swap on updated_at).
                for _ in range(WRITE_TRIES):
                    current, version = db.get_versioned(key)
                    out = _merge(data, base_text, None if current is database._MISSING else current)
                    text = json.dumps(out)
                    if db.put_if(key, text, version):
                        break
                else:
                    raise database.DatabaseError(f'{key}: other writers kept saving it; not saved')
        else:
            out = _merge(data, base_text, _current_text(path)) if base_text is not None else data
            text = json.dumps(out, indent=2)
            # An event's or tenant's folder exists once something is saved in it.
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path + NEXT, 'w') as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            with open(path, 'w') as f:
                f.write(text)
            _warned.discard(path)
    _generation[0] += 1
    _written[path] = _written.get(path, 0) + 1
    if isinstance(data, Doc):
        # What the caller's copy now stands for: a second save from it changes only what it changes.
        data._base = (path, text if out is data else json.dumps(data, indent=None if db.kind != 'files' else 2))


_shared = {}            # path -> (stamp, generation, document)
SHARED_RECHECK = 1.0    # seconds: another pod's change shows up this late at most
_generation = [0]       # bumped by every write here: a write within one mtime tick still counts
_written = {}           # path -> writes here: the LAN cache stats saving must not re-read data.json


def generation(path):
    """Changes whenever this process writes ``path``."""
    return _written.get(path, 0)


def read_shared(path, default=None):
    """Like ``read_json``, for hot read-only paths (who is signed in, their role, which plugins are
    on): parsed once per change, not on every call. Every request asked these several times, and
    each time parsed the whole data.json; at a 400-switch event that was 86% of the server's CPU.
    The document is shared: never change it, copy what you hand on."""
    hit = _shared.get(path)
    now = time.monotonic()
    if hit and hit[1] == generation(path) and now - hit[3] < SHARED_RECHECK and _remote_backend():
        return hit[2]     # on a database, asking for the row's stamp is a query: once a second
    mark = _mark(path)
    if mark is None:
        return read_json(path, default)
    if hit and hit[0] == mark and hit[1] == generation(path):
        _shared[path] = (mark, hit[1], hit[2], now)
        return hit[2]
    written = generation(path)
    doc = read_json(path, default)
    if len(_shared) > 256:
        _shared.clear()
    _shared[path] = (mark, written, doc, now)
    return doc


def _remote_backend():
    from . import database
    return database.backend().kind != 'files'


def _mark(path):
    """``stamp`` plus, for a file, its size and inode: a rewrite by rename, or two writes inside
    one mtime tick, still reads as a change."""
    from . import database
    if database.backend().kind != 'files':
        return stamp(path)
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def stamp(path):
    """Something that changes whenever the document does (for caches that re-read on change):
    the file's mtime, or the row's update time in a database. None when there is no document."""
    from . import database
    db = database.backend()
    if db.kind != 'files':
        return db.updated_at(database.key_for(path, db.root))
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def list_json(folder):
    """The ``*.json`` names in a folder of documents (templates, archived events), from the
    database or the folder."""
    from . import database
    db = database.backend()
    names = set()
    if db.kind != 'files':
        prefix = database.key_for(folder, db.root).rstrip('/') + '/'
        names |= {k[len(prefix):] for k in db.keys(prefix) if '/' not in k[len(prefix):]}
    if os.path.isdir(folder):
        # In a database too: files not imported yet still count (they're taken over when read).
        names |= {n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n))}
    return sorted(n for n in names if n.endswith('.json'))


def delete_json(path):
    """Remove a document. True when there was one."""
    from . import database
    db = database.backend()
    gone = False
    if db.kind != 'files':
        gone = db.delete(database.key_for(path, db.root))
    with _lock:
        if os.path.isfile(path):
            os.remove(path)          # an old file would otherwise come back on the next read
            gone = True
        if os.path.isfile(path + NEXT):
            os.remove(path + NEXT)
    return gone


def unwritable(path=None):
    """Files next to the data file (and its folder) this process can't write, so a save won't 500
    by surprise. Files copied into the Docker volume with ``docker compose cp`` arrive owned by root."""
    folder = os.path.dirname(os.path.abspath(path or DATA_FILE))
    if not os.path.isdir(folder):
        return []
    found = [] if os.access(folder, os.W_OK) else [folder]
    for name in sorted(os.listdir(folder)):
        full = os.path.join(folder, name)
        if os.path.isfile(full) and not os.access(full, os.W_OK):
            found.append(full)
    return found


# ── Tenants and events (issue #466, docs/tenancy.md) ──
#
# Documents belong to a tenant (accounts, settings, plugins, agents) or to one of its events (the
# floor plan, incidents, check-ins, logs). Both are folders under the state folder, named relative
# to it; '' is the state folder itself, where a self-hosted install, its one tenant and its first
# event have always kept everything. So nothing moves until a second event or tenant exists.
#
# The event folder is None unless a request or a ``using`` block picks one: then it is the
# tenant's live event (``floorbit.tenancy``), which is what background workers follow.
_tenant_dir = contextvars.ContextVar('floorbit_tenant_dir', default=None)
_event_dir = contextvars.ContextVar('floorbit_event_dir', default=None)
live_event_dir = None    # set by floorbit.tenancy: () -> the live event's folder


def state_folder():
    return os.path.dirname(os.path.abspath(DATA_FILE))


# Every install serves exactly one tenant per process (docs/tenancy.md): FLOORBIT_TENANT names it,
# and without it the process serves the tenant called ``default``. A self-hosted install is the
# default tenant of its own platform, so it runs the same code as a hosted one.
TENANT_ENV = 'FLOORBIT_TENANT'
DEFAULT_TENANT = 'default'
TENANTS_FOLDER = 'tenants'
_TENANT_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')


def current_tenant():
    """The tenant this process serves: FLOORBIT_TENANT, else ``default``."""
    name = (os.environ.get(TENANT_ENV) or '').strip() or DEFAULT_TENANT
    if not _TENANT_RE.match(name):
        # It becomes a folder and a key prefix: nothing else gets through.
        raise ValueError(f'{TENANT_ENV} must be lower-case letters, digits and -, at most 40 (got {name!r}).')
    return name


def tenant_folder(tenant_id):
    """Where a tenant's documents live, relative to the state folder. The default tenant keeps the
    state folder itself, where every install kept everything before tenants existed: moving them
    would break the compose files that bind-mount data.json alone, and nothing gains from it.
    The others live in tenants/<id>/, which the default tenant's own listings never reach into
    (they read one folder level, and backups take named documents)."""
    return '' if tenant_id == DEFAULT_TENANT else f'{TENANTS_FOLDER}/{tenant_id}'


def tenant_dir():
    chosen = _tenant_dir.get()
    if chosen is not None:
        return chosen
    return tenant_folder(current_tenant())


def event_dir():
    """The current event's folder, relative to the tenant's."""
    chosen = _event_dir.get()
    if chosen is None:
        if live_event_dir is None:
            from . import tenancy  # noqa: F401  (sets live_event_dir; late: it imports store)
        chosen = live_event_dir()
    return chosen


def _join(*parts):
    return os.path.join(state_folder(), *(p for p in parts if p))


def tenant_path(*names):
    """A tenant document or folder: accounts, settings, plugins, archived events, templates."""
    return _join(tenant_dir(), *names)


def event_path(*names):
    """A document or folder of the current event: the floor plan, logs, check-ins, figures."""
    return _join(tenant_dir(), event_dir(), *names)


def _scoped(configured, folder):
    # A path someone configured (CHECKIN_FILE, data.json itself) stays exactly as it is where it
    # always was; elsewhere the same name goes into the tenant's or event's folder.
    if not folder:
        return configured
    return _join(folder, os.path.basename(configured))


def tenant_file(configured=None):
    """data.json of the tenant, or another configured file put in the tenant's folder."""
    return _scoped(configured or DATA_FILE, tenant_dir())


def event_file(configured=None):
    """data.json of the current event, or another configured file put in the event's folder."""
    return _scoped(configured or DATA_FILE, os.path.join(tenant_dir(), event_dir()).strip(os.sep))


@contextmanager
def using(tenant=None, event=None):
    """Read and write the documents of this tenant folder and event folder in this block."""
    tokens = []
    if tenant is not None:
        tokens.append((_tenant_dir, _tenant_dir.set(tenant)))
    if event is not None:
        tokens.append((_event_dir, _event_dir.set(event)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


# Parts of data.json that belong to the tenant, not to one event. The first event shares one file
# with the tenant, as always; a later event's data.json leaves them out, and load_data/save_data
# take them from and put them back into the tenant's (docs/tenancy.md). New tenant-wide parts are
# added here.
TENANT_KEYS = frozenset({
    'auth_users', 'auth_teams', 'auth_roles', 'auth_oidc', 'auth_secret_key', 'api_tokens',
    'app_settings', 'default_settings', 'setup', 'features', 'credentials', 'agents', 'webhooks',
    'runbooks', 'command_templates', 'dashboard_layouts', 'dashboards',
})


def _files():
    """(the event's data.json, the tenant's when it is another file)."""
    path, tenant = event_file(), tenant_file()
    return path, (tenant if os.path.abspath(tenant) != os.path.abspath(path) else None)


def _empty():
    return Doc({
        'inventory':      [],   # every device, made by hand or fed by plugins (inventory.py)
        'seats':          [],   # individual seats
        'seat_blocks':    [],   # seating blocks (rows/sections)
    })


def load_shared():
    """``load_data()`` for hot read-only paths (an event handler per syslog alert), parsed once per
    change of the file (``read_shared``). Shared: never change it."""
    from . import upgrades
    path, tenant_path_ = _files()
    found = read_shared(path)
    if not isinstance(found, dict):
        return _empty()
    if not upgrades.current(found):     # not moved yet (Floorbit moves it at start): never change a shared copy
        return load_data()
    if not tenant_path_:
        return found
    tenant = read_shared(tenant_path_, {})
    out = {k: v for k, v in found.items() if k not in TENANT_KEYS}
    out.update({k: tenant[k] for k in TENANT_KEYS if k in tenant})
    return out


def load_data():
    path, tenant_path_ = _files()
    found = read_json(path)
    if not isinstance(found, dict):
        last = _last_object(path) if found is not None else None
        if found is not None:
            _not_an_object(path, found, last is not None)
        found = _empty() if last is None else last
    if tenant_path_:
        tenant = read_json(tenant_path_, {})
        for key in TENANT_KEYS:
            found.pop(key, None)
            if key in tenant:
                found[key] = tenant[key]
        # What the tenant's parts were, so save_data writes back only the ones the caller changed.
        # A copy: callers change what they got in place.
        found._tenant = json.loads(json.dumps({k: tenant[k] for k in TENANT_KEYS if k in tenant}))
    # After the tenant's parts are noted, so save_data writes back what the steps moved there.
    from . import upgrades
    upgraded = upgrades.apply(found)
    if isinstance(found, Doc):
        found._upgraded = upgraded
    return found


# Features Mike dropped (2026-11-17): their data goes with the next write instead of lingering.
RETIRED_KEYS = ('planner', 'teardown', 'loans')


def save_data(data):
    for key in RETIRED_KEYS:
        data.pop(key, None)
    path, tenant_path_ = _files()
    if not tenant_path_:
        write_json(path, data)
        return
    loaded = getattr(data, '_tenant', None)    # None: a document the caller built itself
    tenant = read_json(tenant_path_, {})
    changed = False
    for key in TENANT_KEYS:
        if key in data:
            if (loaded is None or loaded.get(key) != data[key]) and tenant.get(key) != data[key]:
                tenant[key] = data[key]
                changed = True
        elif loaded is not None and key in loaded and key in tenant:
            tenant.pop(key)
            changed = True
    if changed:
        write_json(tenant_path_, tenant)
    event = Doc({k: v for k, v in data.items() if k not in TENANT_KEYS})
    event._base = getattr(data, '_base', None)
    write_json(path, event)
    if isinstance(data, Doc):
        data._base = event._base
        data._tenant = json.loads(json.dumps({k: data[k] for k in TENANT_KEYS if k in data}))
