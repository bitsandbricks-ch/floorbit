"""Where each machine was seen: MAC, IP, switch port and seat over time (docs/endpoints.md).

The monitoring picture (telemetry's MAC tables and ARP, from Floorbit's own collector or a local
agent) is turned into rows of "this MAC with this IP was on this port" every minute. A row stays
open while it keeps being seen and gets a new one when the machine moves, changes IP or was gone
for ``GAP``. So the crew can search an IP or a MAC fast, and see a port's or a seat's history.

Kept in the database (table ``floorbit_endpoints``, SQLite or Postgres) for ``keep_days()``
(``FLOORBIT_ENDPOINT_DAYS``, 7 by default); with plain files, the last day in memory only. Shown
only to roles with ``seats.view``, like everything else that names the machines at the seats.
"""
import ipaddress
import os
import re
import threading
import time

GAP = 15 * 60                 # gone longer than this: the next sighting is a new row
MEMORY_HOURS = 24
CHUNK = 200                   # rows per INSERT
LIMIT = 200
COLUMNS = ('mac', 'ip', 'device', 'port_key', 'first_seen', 'port', 'seat', 'vlan', 'last_seen')


def keep_days():
    try:
        return max(1, min(365, int(os.environ.get('FLOORBIT_ENDPOINT_DAYS') or 7)))
    except ValueError:
        return 7


def mac_hex(mac):
    """Twelve lowercase hex digits, or None."""
    digits = re.sub(r'[^0-9a-fA-F]', '', str(mac or '')).lower()
    return digits if len(digits) == 12 else None


def mac_text(digits):
    return ':'.join(digits[i:i + 2] for i in range(0, 12, 2)) if digits else ''


def _port_key(port):
    from .syslog import canonical_port
    return canonical_port(port) if port else ''


def _seats():
    """{(switch lowercase, canonical port): seat}: the patch plan and what check-ins learned."""
    from . import cables
    try:
        return cables.port_seats()
    except Exception as exc:  # noqa: BLE001  # no seat names is better than no history
        print(f'[endpoints] seat ports: {exc}')
        return {}


class History:
    def __init__(self, db=None):
        self.db = db
        self._lock = threading.Lock()
        self.open = None              # (mac, ip, device, port_key) -> row, the rows still being seen
        self.memory = []              # without a database
        self.written = 0
        self.error = None
        self._pruned = 0.0

    # ── writing ──
    def _load_open(self, now):
        self.open = {}
        if self.db is None:
            return
        rows = self.db.run(f'SELECT {", ".join(COLUMNS)} FROM floorbit_endpoints WHERE last_seen >= ?',
                           (int(now - GAP),), fetch=True) or []
        for r in rows:
            row = dict(zip(COLUMNS, r, strict=True))
            key = (row['mac'], row['ip'], row['device'], row['port_key'])
            if key not in self.open or self.open[key]['first_seen'] < row['first_seen']:
                self.open[key] = row

    def record(self, sightings, now=None):
        """``sightings``: ``[{mac, ip, device, port, vlan}]`` seen now (ip or port may be empty).
        Returns how many rows it wrote."""
        from .database import DatabaseError
        now = int(time.time() if now is None else now)
        seats = None
        changed = []
        with self._lock:
            try:
                if self.open is None:
                    self._load_open(now)
            except DatabaseError as exc:
                self.error = str(exc)[:200]
                self.open = None
                return 0
            for s in sightings:
                mac = mac_hex(s.get('mac'))
                if not mac:
                    continue
                ip = str(s.get('ip') or '')[:45]
                device = str(s.get('device') or '')[:120]
                port = str(s.get('port') or '')[:120]
                if not device:
                    continue
                key = (mac, ip, device, _port_key(port))
                row = self.open.get(key)
                if row is None or now - row['last_seen'] > GAP:
                    if seats is None:
                        seats = _seats()
                    vlan = s.get('vlan')
                    row = self.open[key] = {
                        'mac': mac, 'ip': ip, 'device': device, 'port_key': key[3], 'first_seen': now,
                        'port': port, 'seat': seats.get((device.lower(), key[3]), '') if port else '',
                        'vlan': int(vlan) if str(vlan or '').isdigit() else None, 'last_seen': now}
                    if self.db is None:
                        self.memory.append(row)
                else:
                    row['last_seen'] = now
                changed.append(row)
            # Rows not seen for a while are closed: forget them here, they stay in the table.
            self.open = {k: r for k, r in self.open.items() if now - r['last_seen'] <= GAP}
            if self.db is None:
                self.memory = [r for r in self.memory if r['last_seen'] >= now - MEMORY_HOURS * 3600]
        if self.db is not None and changed:
            try:
                self._write(changed)
            except DatabaseError as exc:      # the database is away: skip this round, never stop
                self.error = str(exc)[:200]
                return 0
            self.error = None
            if now - self._pruned > 3600:
                self.prune(now)
        self.written += len(changed)
        return len(changed)

    def _write(self, rows):
        marks = '(' + ', '.join('?' * len(COLUMNS)) + ')'
        for i in range(0, len(rows), CHUNK):
            part = rows[i:i + CHUNK]
            args = [r[c] for r in part for c in COLUMNS]
            self.db.run(f'INSERT INTO floorbit_endpoints ({", ".join(COLUMNS)}) VALUES '
                        + ', '.join([marks] * len(part))
                        + ' ON CONFLICT (mac, ip, device, port_key, first_seen) DO UPDATE SET '
                          'last_seen = excluded.last_seen, seat = excluded.seat, vlan = excluded.vlan', args)

    def prune(self, now=None):
        from .database import DatabaseError
        now = time.time() if now is None else now
        self._pruned = now
        if self.db is None:
            return
        try:
            self.db.run('DELETE FROM floorbit_endpoints WHERE last_seen < ?', (int(now - keep_days() * 86400),))
        except DatabaseError as exc:
            self.error = str(exc)[:200]

    # ── reading ──
    def _select(self, where, args, limit):
        if self.db is None:
            return None
        rows = self.db.run(f'SELECT {", ".join(COLUMNS)} FROM floorbit_endpoints WHERE {where} '
                           f'ORDER BY last_seen DESC LIMIT {int(limit)}', args, fetch=True) or []
        return [dict(zip(COLUMNS, r, strict=True)) for r in rows]

    def _memory(self, test, limit):
        with self._lock:
            found = [dict(r) for r in self.memory if test(r)]
        return sorted(found, key=lambda r: r['last_seen'], reverse=True)[:limit]

    def search(self, query, limit=LIMIT):
        """Rows whose IP starts with ``query`` or whose MAC holds it (any notation), newest first."""
        q = str(query or '').strip().lower()[:64]
        if len(q) < 2:
            return []
        digits = re.sub(r'[^0-9a-f]', '', q)
        as_mac = len(digits) >= 4 and not re.fullmatch(r'\d{1,3}(?:\.\d{0,3}){0,3}', q)
        as_ip = bool(re.fullmatch(r'[0-9a-f.:]+', q)) and (q.count('.') or q.count(':') or q.isdigit())
        if not as_mac and not as_ip:
            return []
        clauses, args = [], []
        if as_ip:
            clauses.append('ip LIKE ?')
            args.append(q.replace('%', '').replace('_', '') + '%')
        if as_mac:
            clauses.append('mac LIKE ?')
            args.append(f'%{digits}%')
        rows = self._select(' OR '.join(clauses), args, limit)
        if rows is None:
            rows = self._memory(lambda r: (as_ip and r['ip'].startswith(q)) or (as_mac and digits in r['mac']), limit)
        return [_public(r) for r in rows]

    def at_port(self, device, port, limit=LIMIT):
        device, key = str(device or ''), _port_key(port)
        rows = self._select('LOWER(device) = ? AND port_key = ?', (device.lower(), key), limit)
        if rows is None:
            rows = self._memory(lambda r: r['device'].lower() == device.lower() and r['port_key'] == key, limit)
        return [_public(r) for r in rows]

    def at_seat(self, seat, limit=LIMIT):
        """What was on the seat's port: rows stored with the seat, and rows on the port the seat is
        on now (the patch plan or a check-in may have named it later)."""
        seat = str(seat or '')
        ports = [k for k, v in _seats().items() if v == seat]
        where, args = ['seat = ?'], [seat]
        for device, key in ports[:8]:
            where.append('(LOWER(device) = ? AND port_key = ?)')
            args += [device, key]
        rows = self._select(' OR '.join(where), args, limit)
        if rows is None:
            rows = self._memory(lambda r: r['seat'] == seat or (r['device'].lower(), r['port_key']) in ports, limit)
        return [_public(r) for r in rows]

    def status(self):
        return {'store': 'database' if self.db is not None else 'memory', 'written': self.written,
                'open': len(self.open or {}), 'keep_days': keep_days() if self.db is not None else 1,
                'error': self.error}


def _public(r):
    return {'mac': mac_text(r['mac']), 'ip': r['ip'] or None, 'device': r['device'], 'port': r['port'] or None,
            'seat': r['seat'] or None, 'vlan': r['vlan'], 'first_seen': r['first_seen'], 'last_seen': r['last_seen']}


def looks_like_address(query):
    """Is it worth asking the history? An IP (or its start) or a MAC (or a part of one)."""
    q = str(query or '').strip()
    if len(q) < 3:
        return False
    if mac_hex(q) or re.fullmatch(r'(?:[0-9a-fA-F]{2}[:.-]){1,5}[0-9a-fA-F]{0,2}', q):
        return True
    if re.fullmatch(r'\d{1,3}(?:\.\d{0,3}){1,3}', q):
        return True
    try:
        ipaddress.ip_address(q)
        return True
    except ValueError:
        return False


_history = None


def history():
    global _history
    if _history is None:
        from . import database
        backend = database.backend()
        _history = History(backend if hasattr(backend, 'run') else None)
    return _history


def reset():
    global _history
    _history = None
