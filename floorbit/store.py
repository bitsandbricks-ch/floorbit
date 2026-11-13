"""The floor plan's data file (switch positions, seat blocks, settings, accounts).

Everything lives in one JSON file, ``DATA_FILE``, read and written whole.
"""
import json
import os

DATA_FILE = 'data.json'


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {
        'switches':       [],   # manual mode switch list
        'cached_devices': [],   # netbox mode: cached device list
        'positions':      {},   # netbox mode: {str(device_id): {x, y}}
        'seats':          [],   # individual seats
        'seat_blocks':    [],   # seating blocks (rows/sections)
    }


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
