"""Crew notes on a seat (issue #180): one short note per seat, such as "cable swapped at 14:20"
or "brought their own switch, leave it", so the next tech at the seat knows what was done.

Kept in data.json under ``seat_notes`` as ``{seat: {text, by, at}}``. Starting a new event clears
them, because they are about this event's cables and players. Notes are for the crew: reading and
writing need ``incidents.work``, and the plan only tells everyone else that a seat has one.
"""
import threading
import time

from .store import load_data, save_data

KEY = 'seat_notes'
MAX_TEXT = 500
_lock = threading.Lock()


def all_notes(data=None):
    data = load_data() if data is None else data
    notes = data.get(KEY)
    return {s: n for s, n in notes.items() if isinstance(n, dict) and n.get('text')} if isinstance(notes, dict) else {}


def get(seat, data=None):
    return all_notes(data).get(seat)


def set_note(seat, text, by=None, now=None):
    """Save the seat's note, or remove it when ``text`` is empty. Returns the note (or None)."""
    text = str(text or '').strip()[:MAX_TEXT]
    with _lock:
        data = load_data()
        notes = all_notes(data)
        if text:
            notes[seat] = {'text': text, 'by': by, 'at': time.time() if now is None else now}
        else:
            notes.pop(seat, None)
        data[KEY] = notes
        save_data(data)
    return notes.get(seat)


def clear():
    with _lock:
        data = load_data()
        if data.pop(KEY, None) is not None:
            save_data(data)
