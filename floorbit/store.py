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
import json
import os
import threading
import time

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


def _doc(found, path, text):
    if not isinstance(found, dict):
        return found
    doc = Doc(found)
    doc._base = (path, text)
    return doc


def _merge(data, base_text, current_text):
    """What to write: ``data`` with the top-level parts nobody here changed taken from the current
    document. Background tasks and requests each load the whole document, change their own part
    and save it whole: without this, one saving a copy it loaded a moment earlier puts back
    everything another changed meanwhile (an incident marked fixed came back open)."""
    if current_text is None or current_text == base_text:
        return data     # nobody wrote in between: the usual case, no parsing
    try:
        base, current = json.loads(base_text), json.loads(current_text)
    except (TypeError, ValueError):
        return data
    if not isinstance(base, dict) or not isinstance(current, dict):
        return data
    out = dict(current)
    for key in set(base) | set(data):
        if key in data:
            if key not in base or data[key] != base[key]:
                out[key] = data[key]            # the caller changed it: theirs wins, as before
        else:
            out.pop(key, None)                  # the caller removed it
    return out


def read_json(path, default=None):
    """The document's JSON, or ``default`` when it doesn't exist. From the database when
    FLOORBIT_DATABASE_URL names one (floorbit/database.py), else from the file. A caller whose
    default is an object (``{}``) always gets an object back."""
    found = _read_json(path, default)
    if isinstance(default, dict) and not isinstance(found, dict):
        _not_an_object(path, found)
        return default
    return found


def _not_an_object(path, found):
    if path not in _warned:
        _warned.add(path)
        print(f'[store] {path} holds {type(found).__name__}, not an object (edited by hand?); '
              'starting from empty until the next save')


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
            if base_text is not None:
                current = db.get_text(key)
                out = _merge(data, base_text, None if current is database._MISSING else current)
            else:
                out = data
            text = json.dumps(out)
            db.put(key, text)
        else:
            out = _merge(data, base_text, _current_text(path)) if base_text is not None else data
            text = json.dumps(out, indent=2)
            with open(path + NEXT, 'w') as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            with open(path, 'w') as f:
                f.write(text)
            _warned.discard(path)
    if isinstance(data, Doc):
        # What the caller's copy now stands for: a second save from it changes only what it changes.
        data._base = (path, text if out is data else json.dumps(data, indent=None if db.kind != 'files' else 2))


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


def load_data():
    found = read_json(DATA_FILE)
    if isinstance(found, dict):
        return found
    if found is not None:
        _not_an_object(DATA_FILE, found)
    return {
        'inventory':      [],   # every device, made by hand or fed by plugins (inventory.py)
        'seats':          [],   # individual seats
        'seat_blocks':    [],   # seating blocks (rows/sections)
    }


# Features Mike dropped (2026-11-17): their data goes with the next write instead of lingering.
RETIRED_KEYS = ('planner', 'teardown')


def save_data(data):
    for key in RETIRED_KEYS:
        data.pop(key, None)
    write_json(DATA_FILE, data)
