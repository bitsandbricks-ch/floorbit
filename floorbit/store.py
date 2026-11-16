"""The floor plan's data file (inventory, seat blocks, settings, accounts).

Everything lives in one JSON file, ``DATA_FILE``, read and written whole.

It is written in place, not swapped in by a rename, because older compose files bind-mount the single
file and a rename onto a bind mount fails. So a reader can catch it between the truncate and the
write. ``read_json`` and ``write_json`` close that gap: inside one process a lock keeps them apart,
and a reader in another process (more than one worker) that finds half a file waits and reads again.
Every reader and writer of data.json (here, auth/ and the settings store) goes through them.
"""
import json
import os
import threading
import time

# Compose keeps it in the state folder with everything else (docs/install.md).
DATA_FILE = os.environ.get('FLOORBIT_DATA_FILE') or 'data.json'
READ_TRIES = 6            # about 0.3 s in all before a half-written file counts as broken

_lock = threading.RLock()


def read_json(path, default=None):
    """The document's JSON, or ``default`` when it doesn't exist. From the database when
    FLOORBIT_DATABASE_URL names one (floorbit/database.py), else from the file."""
    from . import database
    db = database.backend()
    if db.kind != 'files':
        key = database.key_for(path, db.root)
        found = db.get(key)
        if found is not database._MISSING:
            return found
        # Not in the database yet: take the file's content over, once (docs/database.md).
        found = _read_file(path, database._MISSING)
        if found is database._MISSING:
            return default
        with _lock:
            if db.get(key) is database._MISSING:
                db.put(key, json.dumps(found))
        return found
    return _read_file(path, default)


def _read_file(path, default):
    for attempt in range(READ_TRIES):
        try:
            with _lock, open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except json.JSONDecodeError:
            if attempt == READ_TRIES - 1:
                raise
            time.sleep(0.02 * (attempt + 1))   # another process is writing it right now
    return default


def write_json(path, data):
    # Serialised first and written in one go, so the file is empty or half-written for as short
    # a time as possible; a failure to serialise leaves the old file untouched.
    from . import database
    db = database.backend()
    if db.kind != 'files':
        db.put(database.key_for(path, db.root), json.dumps(data))
        return
    text = json.dumps(data, indent=2)
    with _lock, open(path, 'w') as f:
        f.write(text)


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
    if found is not None:
        return found
    return {
        'inventory':      [],   # every device, made by hand or fed by plugins (inventory.py)
        'seats':          [],   # individual seats
        'seat_blocks':    [],   # seating blocks (rows/sections)
    }


def save_data(data):
    write_json(DATA_FILE, data)
