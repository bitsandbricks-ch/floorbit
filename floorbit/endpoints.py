"""Where each machine was seen: MAC, IP, switch port and seat over time (docs/endpoints.md).

The monitoring picture (telemetry's MAC tables and ARP, from Floorbit's own collector or a local
agent) is turned into rows of "this MAC with this IP was on this port" every minute. A row stays
open while it keeps being seen and gets a new one when the machine moves, changes IP or was gone
for ``GAP``. So the crew can search an IP or a MAC fast, and see a port's or a seat's history.

Kept in the database (table ``floorbit_endpoints``, SQLite or Postgres) for ``keep_days()``
(``FLOORBIT_ENDPOINT_DAYS``, 7 by default). Shown
only to roles with ``seats.view``, like everything else that names the machines at the seats.
"""
import ipaddress
import os
import re
import threading
import time

GAP = 15 * 60                 # gone longer than this: the next sighting is a new row
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


def _text(value, size):
    """A column's text: Postgres refuses a NUL byte, and one bad row would fail its whole batch
    again on every report while it stays open."""
    return str(value or '').replace('\x00', '')[:size]


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
    def __init__(self, db):
        self.db = db                  # floorbit.database.Sql
        self._lock = threading.Lock()
        self.open = None              # (mac, ip, device, port_key) -> row, the rows still being seen
        self.written = 0
        self.error = None
        self._pruned = 0.0

    # ── writing ──
    def _load_open(self, now):
        self.open = {}
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
        changed, dropped = [], []
        with self._lock:
            try:
                if self.open is None:
                    self._load_open(now)
            except DatabaseError as exc:
                self.error = str(exc)[:200]
                self.open = None
                return 0
            # ARP (the core) and MAC tables (the access switches) arrive in separate rounds: a MAC
            # can show up without its port for a round. That row is the same sighting, not a
            # machine behind a router, so it is folded into the port's row (issue #873).
            ported, portless = set(), {}
            for k in self.open:
                if k[3]:
                    ported.add((k[0], k[1]))
                else:
                    portless.setdefault((k[0], k[1]), []).append(k)
            for s in sightings:
                mac = mac_hex(s.get('mac'))
                if not mac:
                    continue
                ip = _text(s.get('ip'), 45)
                device = _text(s.get('device'), 120)
                port = _text(s.get('port'), 120)
                if not device:
                    continue
                key = (mac, ip, device, _port_key(port))
                if not key[3] and (mac, ip) in ported:
                    continue        # the access switch's entry aged out first: still on its port
                row = self.open.get(key)
                if row is None or now - row['last_seen'] > GAP:
                    if seats is None:
                        seats = _seats()
                    vlan = s.get('vlan')
                    row = self.open[key] = {
                        'mac': mac, 'ip': ip, 'device': device, 'port_key': key[3], 'first_seen': now,
                        'port': port, 'seat': seats.get((device.lower(), key[3]), '') if port else '',
                        'vlan': int(vlan) if str(vlan or '').isdigit() else None, 'last_seen': now}
                    if key[3]:
                        ported.add((mac, ip))
                        for old in portless.pop((mac, ip), ()):
                            early = self.open.pop(old, None)
                            if early is None:
                                continue
                            dropped.append(early)
                            row['first_seen'] = min(row['first_seen'], early['first_seen'])
                            changed[:] = [c for c in changed if c is not early]
                elif now > row['last_seen']:
                    row['last_seen'] = now
                else:
                    continue        # an older batch (an agent's spool, a second agent): nothing new
                changed.append(row)
            # Rows not seen for a while are closed: forget them here, they stay in the table.
            latest = max([now, *(r['last_seen'] for r in self.open.values())])
            self.open = {k: r for k, r in self.open.items() if latest - r['last_seen'] <= GAP}
        if changed:
            try:
                self._drop(dropped)
                self._write(changed)
            except DatabaseError as exc:      # the database is away: skip this round, never stop
                self.error = str(exc)[:200]
                return 0
            self.error = None
            if now - self._pruned > 3600:
                self.prune(now)
        self.written += len(changed)
        return len(changed)

    def _drop(self, rows):
        for r in rows:
            self.db.run('DELETE FROM floorbit_endpoints WHERE mac = ? AND ip = ? AND device = ? AND port_key = ? '
                        'AND first_seen = ?', (r['mac'], r['ip'], r['device'], r['port_key'], r['first_seen']))

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
        try:
            self.db.run('DELETE FROM floorbit_endpoints WHERE last_seen < ?', (int(now - keep_days() * 86400),))
        except DatabaseError as exc:
            self.error = str(exc)[:200]

    # ── reading ──
    def _select(self, where, args, limit):
        rows = self.db.run(f'SELECT {", ".join(COLUMNS)} FROM floorbit_endpoints WHERE {where} '
                           f'ORDER BY last_seen DESC LIMIT {int(limit)}', args, fetch=True) or []
        return [dict(zip(COLUMNS, r, strict=True)) for r in rows]

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
        # The exact IP or MAC first, then the newest: "192.0.2.2" before 192.0.2.254.
        rows.sort(key=lambda r: (r['ip'] != q and r['mac'] != digits, -r['last_seen']))
        return [_public(r) for r in rows]

    def at_port(self, device, port, limit=LIMIT):
        device, key = str(device or ''), _port_key(port)
        rows = self._select('LOWER(device) = ? AND port_key = ?', (device.lower(), key), limit)
        return [_public(r) for r in rows]

    def at_device(self, device, limit=LIMIT):
        """Everything seen on one switch's ports, newest first (its MAC/IP tab)."""
        return [_public(r) for r in self._select('LOWER(device) = ?', (str(device or '').lower(),), limit)]

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
        return [_public(r) for r in rows]

    def status(self):
        return {'store': 'database', 'written': self.written, 'open': len(self.open or {}),
                'keep_days': keep_days(), 'error': self.error}


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
        _history = History(database.backend())
    return _history


def reset():
    global _history
    _history = None
