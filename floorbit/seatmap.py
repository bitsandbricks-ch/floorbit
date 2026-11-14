"""The seat mapping: which IP, MAC and nick belong to which seat.

Floorbit merges it from seat sources (integrations/seat_sources.py): the entries people type in by
hand (this module, stored in data.json under ``seat_map``), plugins with ``uses: [mapping]``, the
check-in page, ``seats.json`` and the HTTP source. Hand entries always come first, so a field set
here wins over every other source; fields left empty are filled from the others. See
docs/seat-mapping.md.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import re
import threading
import time

SEAT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _\-]{0,15}$')
MAC_RE = re.compile(r'^[0-9a-f]{12}$')
# Field names as the seat sources use them (check-in, seats.json, HTTP).
FIELDS = {'ip_address': 'ip', 'mac_address': 'mac', 'username': 'nick', 'note': 'note'}
CSV_COLUMNS = ('seat', 'ip', 'mac', 'nick', 'note')
MAX_ROWS = 5000
MAX_CSV_BYTES = 1024 * 1024

_lock = threading.RLock()


class MappingError(ValueError):
    """Bad input; the message is shown."""


def clean_seat(seat):
    seat = str(seat or '').strip()
    if not SEAT_RE.match(seat):
        raise MappingError(f'"{seat[:20]}" is not a seat label (letters, digits, space, - and _, up to 16)')
    return seat


def clean_ip(value):
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise MappingError(f'"{value[:45]}" is not an IP address') from None


def clean_mac(value):
    """Any common spelling (aa-bb-.., aabb.ccdd.eeff, AABBCC..) becomes aa:bb:cc:dd:ee:ff."""
    raw = str(value or '').strip()
    if not raw:
        return ''
    hexdigits = re.sub(r'[\s:.\-]', '', raw).lower()
    if not MAC_RE.match(hexdigits):
        raise MappingError(f'"{raw[:20]}" is not a MAC address')
    return ':'.join(hexdigits[i:i + 2] for i in range(0, 12, 2))


def _clean_text(value, limit, what):
    value = str(value or '').strip()
    if '\n' in value or '\r' in value:
        raise MappingError(f'{what} must be one line')
    return value[:limit]


def clean_entry(body):
    """{'ip', 'mac', 'nick', 'note'} from a request or a CSV row, checked and normalised."""
    return {
        'ip_address': clean_ip(body.get('ip')),
        'mac_address': clean_mac(body.get('mac')),
        'username': _clean_text(body.get('nick'), 64, 'Nick'),
        'note': _clean_text(body.get('note'), 200, 'Note'),
    }


def entries(data):
    raw = data.get('seat_map')
    return raw if isinstance(raw, dict) else {}


def put(data, seat, body, user=None):
    """Set a seat's hand entry. Empty fields are dropped; an entry with nothing left is removed.
    Returns the entry, or None when it was removed."""
    seat = clean_seat(seat)
    entry = {k: v for k, v in clean_entry(body).items() if v}
    with _lock:
        table = data.setdefault('seat_map', {})
        if not entry:
            table.pop(seat, None)
            return None
        entry['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        if user:
            entry['updated_by'] = str(user)[:64]
        table[seat] = entry
        return entry


def remove(data, seat):
    with _lock:
        return entries(data).pop(str(seat), None) is not None


def public(seat, entry):
    """A hand entry with the short field names the page and the CSV use."""
    return {'seat': seat, **{short: entry.get(long, '') for long, short in FIELDS.items()},
            'updated_at': entry.get('updated_at'), 'updated_by': entry.get('updated_by')}


# ── CSV ────────────────────────────────────────────────────────────────────────────────────

def _cell(value):
    # People type these: keep a spreadsheet from running one as a formula.
    value = str(value or '')
    return "'" + value if value[:1] in ('=', '+', '-', '@', '\t', '\r') else value


def to_csv(data):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    for seat in sorted(entries(data), key=_natural):
        row = public(seat, entries(data)[seat])
        writer.writerow([_cell(row[c]) for c in CSV_COLUMNS])
    return out.getvalue()


def _natural(seat):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', seat)]


def parse_csv(text):
    """Every row checked before anything is written. Returns (rows, errors): rows is
    {seat: entry}, errors a list of "line N: why". A leading ' (from our own export) is dropped."""
    if len(text.encode('utf-8')) > MAX_CSV_BYTES:
        raise MappingError('The file is larger than 1 MB')
    text = text.lstrip('﻿')
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    if 'seat' not in header:
        raise MappingError('The first line must name the columns: seat, ip, mac, nick, note')
    unknown = [h for h in header if h and h not in CSV_COLUMNS]
    if unknown:
        raise MappingError(f"Unknown column(s): {', '.join(unknown)}")
    reader.fieldnames = header
    rows, errors = {}, []
    for n, raw in enumerate(reader, start=2):
        if n - 1 > MAX_ROWS:
            errors.append(f'line {n}: more than {MAX_ROWS} rows; stopped')
            break
        values = {k: (v or '').strip() for k, v in raw.items() if k}
        values = {k: v[1:] if v.startswith("'") else v for k, v in values.items()}
        if not any(values.values()):
            continue
        try:
            seat = clean_seat(values.get('seat'))
            if seat in rows:
                raise MappingError(f'seat {seat} is in the file twice')
            rows[seat] = {k: v for k, v in clean_entry(values).items() if v}
        except MappingError as exc:
            errors.append(f'line {n}: {exc}')
    return rows, errors


def import_rows(data, rows, replace=False, user=None):
    """Write checked rows. ``replace`` drops hand entries the file doesn't have."""
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    with _lock:
        table = data.setdefault('seat_map', {})
        added = sum(1 for s in rows if s not in table)
        removed = 0
        if replace:
            removed = sum(1 for s in table if s not in rows)
            table.clear()
        for seat, entry in rows.items():
            if not entry:
                if table.pop(seat, None) is not None:
                    removed += 1
                continue
            table[seat] = {**entry, 'updated_at': stamp, **({'updated_by': str(user)[:64]} if user else {})}
        return {'added': added, 'updated': len(rows) - added, 'removed': removed}


def clean_feed(raw):
    """A plugin's {seat: {ip, mac, nick}} checked; bad entries are dropped. Returns (mapping, skipped)."""
    if not isinstance(raw, dict):
        raise MappingError('the plugin must return a dict of seat: {ip, mac, nick}')
    out, skipped = {}, 0
    for seat, entry in list(raw.items())[:MAX_ROWS]:
        try:
            if not isinstance(entry, dict):
                raise MappingError('not a dict')
            clean = clean_entry({'ip': entry.get('ip') or entry.get('ip_address'),
                                 'mac': entry.get('mac') or entry.get('mac_address'),
                                 'nick': entry.get('nick') or entry.get('username')})
            out[clean_seat(seat)] = {k: v for k, v in clean.items() if v and k != 'note'}
        except MappingError:
            skipped += 1
    return out, skipped
