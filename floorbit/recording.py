"""Full-event recording (issue #104): the whole event, for the replay, compacted as it gets older.

The 24-hour replay (floorbit/stats.py) keeps every seat change. This keeps a frame every five
minutes for as long as the event runs: bandwidth, seats online, which seats were online, which had
an open incident, and per seat block how many seats were online, their traffic and open incidents
(for the heatmap over time). Seat numbers and numbers only: no nicks, IPs or MACs.

Older frames are thinned out: every 5 minutes for the last day, every 30 minutes for the last week,
then every hour. Frames go to ``recording.jsonl`` next to data.json (or ``RECORDING_FILE``); it
starts over with "Start a new event" on the report page.
"""
import contextlib
import json
import os
import threading

from . import store

STEP = 300
DAY = 24 * 3600
# (frames younger than this, are kept this far apart)
TIERS = ((DAY, STEP), (7 * DAY, 1800), (float('inf'), 3600))
COMPACT_EVERY = 3600
MAX_FRAMES = 5000      # hourly for 200 days and more: a forgotten "new event" can't fill the disk
_lock = threading.Lock()
_state = {'last': None, 'compacted': 0.0}


def path():
    return os.environ.get('RECORDING_FILE') or os.path.join(
        os.path.dirname(os.path.abspath(store.DATA_FILE)), 'recording.jsonl')


def _blocks(data):
    """{seat: block name} for the placed seat blocks."""
    from .power import block_rows
    out = {}
    for b in data.get('seat_blocks') or []:
        name = str(b.get('name') or '').upper() or '?'
        for row in block_rows(b):
            for seat in row:
                out[seat] = name
    return out


def frame(sample, seat_bps, open_seats, data):
    """One frame from a stats read. ``seat_bps`` is {seat: bps} of the seats online."""
    of = _blocks(data)
    blocks = {}
    for seat, block in of.items():
        row = blocks.setdefault(block, [0, 0, 0, 0])   # seats, online, bps, open incidents
        row[0] += 1
        if seat in seat_bps:
            row[1] += 1
            row[2] += int(seat_bps[seat] or 0)
        if seat in open_seats:
            row[3] += 1
    return {'t': round(sample['t'], 1), 'down': sample['down'], 'up': sample['up'], 'online': sample['online'],
            'seats': sorted(seat_bps), 'incidents': sorted(s for s in open_seats if s),
            'blocks': blocks}


def capture(sample, seat_bps, open_seats, data, now=None):
    """Write a frame if the last one is STEP or more ago. Returns the frame or None."""
    now = sample['t'] if now is None else now
    with _lock:
        last = _state['last']
        if last is None:
            last = _state['last'] = _last_t()
        if last is not None and now - last < STEP - 5:
            return None
        out = frame(sample, seat_bps, open_seats, data)
        try:
            with open(path(), 'a', encoding='utf-8') as f:
                f.write(json.dumps(out, separators=(',', ':')) + '\n')
        except OSError as exc:   # a full disk must not stop the port watch
            print(f'[recording] could not write a frame: {exc}')
            return None
        _state['last'] = now
        if now - _state['compacted'] >= COMPACT_EVERY:
            _compact(now)
            _state['compacted'] = now
    return out


def _read():
    try:
        with open(path(), encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue   # a line cut short by a crash
        if isinstance(row, dict) and isinstance(row.get('t'), (int, float)):
            out.append(row)
    return sorted(out, key=lambda r: r['t'])


def _last_t():
    rows = _read()
    return rows[-1]['t'] if rows else None


def thin(frames, now):
    """Keep frames at least their tier's spacing apart, by age. Oldest first in, oldest first out."""
    kept, last = [], None
    for row in frames:
        age = now - row['t']
        gap = next(g for limit, g in TIERS if age < limit)
        if last is None or row['t'] - last >= gap - 5:
            kept.append(row)
            last = row['t']
    return kept[-MAX_FRAMES:]


def _compact(now):
    rows = _read()
    kept = thin(rows, now)
    if len(kept) == len(rows):
        return
    tmp = path() + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            for row in kept:
                f.write(json.dumps(row, separators=(',', ':')) + '\n')
        os.replace(tmp, path())
    except OSError as exc:
        print(f'[recording] could not compact: {exc}')


def frames():
    with _lock:
        return _read()


def clear():
    with _lock:
        with contextlib.suppress(OSError):
            os.remove(path())
        _state['last'] = None
