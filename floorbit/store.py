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
    """The file's JSON, or ``default`` when it doesn't exist."""
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
    text = json.dumps(data, indent=2)
    with _lock, open(path, 'w') as f:
        f.write(text)


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
