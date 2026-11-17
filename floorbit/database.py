"""Where Floorbit keeps its documents: files, SQLite or Postgres (issue #464).

Floorbit's state is a set of JSON documents: data.json (the floor plan, accounts, settings), the
saved floor plan templates, archived events, plugin state and so on. Each is read and written whole
through ``store.read_json`` and ``store.write_json``, keyed by its path. This module decides where
those documents live:

- **files** (no ``FLOORBIT_DATABASE_URL``): JSON files under the state folder, as always.
- **SQLite** (``sqlite:////app/state/floorbit.db``): one file, safe to share between processes.
- **Postgres** (``postgresql://user:password@host/floorbit``): for hosted and larger setups.

In a database, a document's key is its path relative to the state folder (``data.json``,
``templates/abc.json``). A document the database doesn't have yet is imported from its file on first
read, once; after that the file is no longer read or written (docs/database.md).

The schema is versioned: ``MIGRATIONS`` runs in order, each once, recorded in ``floorbit_schema``.
The same statements run on SQLite and Postgres, so they stay plain SQL.
"""
import json
import os
import threading
import time
from contextlib import contextmanager, suppress

ENV = 'FLOORBIT_DATABASE_URL'
# How many connections one Floorbit process opens at most (docs/database.md), and how long a
# thread waits for a free one before the request fails.
POOL_ENV = 'FLOORBIT_DATABASE_POOL'
POOL_DEFAULT = 5
POOL_WAIT = 30.0

# Plain SQL both databases take, or {kind: SQL} where they differ. Add a step at the end; never
# change one that has shipped.
MIGRATIONS = (
    """CREATE TABLE floorbit_documents (
        doc_key VARCHAR(512) PRIMARY KEY,
        body TEXT NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL
    )""",
    # Append-only logs (audit log, timeline, check-in history, recording): one row per line.
    {'sqlite': """CREATE TABLE floorbit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_key VARCHAR(512) NOT NULL,
        line TEXT NOT NULL
    )""", 'postgres': """CREATE TABLE floorbit_log (
        id BIGSERIAL PRIMARY KEY,
        log_key VARCHAR(512) NOT NULL,
        line TEXT NOT NULL
    )"""},
    'CREATE INDEX floorbit_log_by_key ON floorbit_log (log_key, id)',
)


class DatabaseError(RuntimeError):
    pass


class DatabaseUnavailable(DatabaseError):
    """The database doesn't answer right now. Floorbit keeps running on the last copies it read,
    refuses to save, and keeps trying in the background (``watch``); see docs/database.md."""


# Waits between tries while the database is away: short at first, then every 30 s at most.
RETRY_FIRST, RETRY_MAX = 1.0, 30.0
# While it answers, ask this often, so the banner and /healthz notice an outage without a request.
PROBE_EVERY = 15.0


def _unreachable(exc):
    """The driver's way of saying the server is gone (refused, dropped, restarting, disk gone),
    as opposed to a mistake in a statement. psycopg says so by the error's type; sqlite3 calls
    nearly everything OperationalError ("no such table" too), so there the message decides."""
    name = type(exc).__name__
    if name not in ('OperationalError', 'InterfaceError', 'ConnectionTimeout'):
        return False
    if type(exc).__module__ != 'sqlite3':
        return True
    text = str(exc).lower()
    return any(m in text for m in ('unable to open', 'disk i/o', 'closed', 'no such file', 'not a database'))


def _redact(url):
    """The URL without its password, for logs and errors."""
    if '@' not in url or '://' not in url:
        return url
    scheme, rest = url.split('://', 1)
    creds, host = rest.rsplit('@', 1)
    user = creds.split(':', 1)[0]
    return f'{scheme}://{user}:***@{host}' if ':' in creds else f'{scheme}://{user}@{host}'


class Files:
    """The JSON files themselves (the default)."""
    kind = 'files'

    def __init__(self, root):
        self.root = root

    def describe(self):
        return f'files in {self.root}'


def _wal(conn, tries=50):
    """WAL mode, so readers don't wait for a writer. It is kept in the file: only the first
    connection switches it. Switching needs the file to itself and SQLite answers "locked" at
    once instead of waiting, so while another connection writes, try again a little later."""
    import sqlite3
    for attempt in range(tries):
        try:
            if conn.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'wal':
                return
            conn.execute('PRAGMA journal_mode=WAL')
            return
        except sqlite3.OperationalError:
            if attempt == tries - 1:
                raise
            time.sleep(0.05 + 0.01 * attempt)


class Sql:
    """SQLite or Postgres: one table of documents. ``connect()`` gives a DB-API connection."""

    def __init__(self, url, root):
        self.url, self.root = url, root
        # A small shared pool instead of a connection per thread: Floorbit runs a few dozen
        # threads (gunicorn's request threads, one per live-update tab, and every background
        # watcher), and a connection each used up the slots of a shared Postgres.
        self.pool_size = max(1, int(os.environ.get(POOL_ENV) or POOL_DEFAULT))
        self._idle = []                                   # connections nobody holds, newest last
        self._slots = threading.BoundedSemaphore(self.pool_size)
        self._lock = threading.Lock()
        self._ready = False
        # The last copy of each document read or written, so pages keep working while the
        # database is away: key -> (body, updated_at). Bodies, not parsed JSON: callers change
        # what they get, so each read parses its own copy.
        self._docs = {}
        self._keys = {}
        self._gen = 0         # bumped by close(): connections borrowed before it don't come back
        self.down = None      # {'since', 'error', 'wait', 'next_try'} while it doesn't answer
        if url.startswith('sqlite:///'):
            self.kind, self.mark = 'sqlite', '?'
            self.path = url[len('sqlite:///'):] or ':memory:'
        elif url.startswith(('postgresql://', 'postgres://')):
            self.kind, self.mark = 'postgres', '%s'
        else:
            raise DatabaseError(f'{ENV} must start with sqlite:/// or postgresql:// (got {_redact(url)}).')

    def describe(self):
        return f'{self.kind} ({_redact(self.url)})'

    def _connect(self):
        if self.kind == 'sqlite':
            import sqlite3
            folder = os.path.dirname(os.path.abspath(self.path))
            if self.path != ':memory:' and not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
            # isolation_level=None: we say BEGIN ourselves. A busy timeout instead of "database is
            # locked" when the flow collector and the web app write at the same moment.
            conn = sqlite3.connect(self.path, timeout=10, isolation_level=None, check_same_thread=False)
            conn.execute('PRAGMA busy_timeout=10000')
            _wal(conn)
            return conn
        try:
            import psycopg
        except ImportError as exc:      # the image has it; a bare `pip install -r` might not
            raise DatabaseError('Postgres needs the psycopg package (pip install "psycopg[binary]").') from exc
        # A short timeout: while the server is away, a request shouldn't hang on it for long.
        return psycopg.connect(self.url, autocommit=True, connect_timeout=5)

    # ── up and down ──

    def _mark_down(self, exc):
        with self._lock:
            first = self.down is None
            wait = RETRY_FIRST if first else min(RETRY_MAX, self.down['wait'] * 2)
            self.down = {'since': time.time() if first else self.down['since'], 'error': str(exc),
                         'wait': wait, 'next_try': time.monotonic() + wait}
        if first:
            print(f"[store] The database {self.describe()} doesn't answer ({exc}). Pages show the "
                  "last copies read and saving is off until it is back; trying again in the background.",
                  flush=True)
        return DatabaseUnavailable(f'{self.describe()}: {exc}')

    def _mark_up(self):
        with self._lock:
            was, self.down = self.down, None
        if was:
            print(f"[store] The database answers again after {time.time() - was['since']:.0f} s.", flush=True)

    def _open(self):
        """A new connection, the schema brought up to date on the first. While the database is
        away, only one try per wait (``RETRY_*``): the rest give up at once."""
        down = self.down
        if down and time.monotonic() < down['next_try']:
            raise DatabaseUnavailable(f"{self.describe()}: {down['error']}")
        try:
            c = self._connect()
        except DatabaseError:
            raise
        except Exception as exc:  # the driver's own error types differ
            raise self._mark_down(exc) from exc
        if not self._ready:
            with self._lock:
                if not self._ready:
                    try:
                        migrate(self, c)
                    except Exception as exc:
                        _close_quietly(c)
                        if _unreachable(exc):
                            raise self._mark_down(exc) from exc
                        raise DatabaseError(f'{self.describe()}: {exc}') from exc
                    self._ready = True
        return c

    def conn(self):
        """A new connection of the caller's own, with the schema brought up to date. The caller
        closes it; everything else borrows one from the pool with ``connection()``."""
        return self._open()

    @contextmanager
    def connection(self):
        """Borrow a connection from the pool for one statement or one transaction. At most
        ``FLOORBIT_DATABASE_POOL`` are open; a thread that finds them all busy waits for one."""
        if not self._slots.acquire(timeout=POOL_WAIT):
            raise DatabaseError(f'{self.describe()}: all {self.pool_size} connections busy for {POOL_WAIT:.0f} s')
        c = None
        try:
            with self._lock:
                gen = self._gen
                c = self._idle.pop() if self._idle else None
            if c is None:
                c = self._open()
            yield c
        except BaseException:
            # The connection may be mid-transaction or broken: don't hand it to the next caller.
            if c is not None:
                _close_quietly(c)
                c = None
            raise
        finally:
            if c is not None and not getattr(c, 'closed', False):
                with self._lock:
                    keep = gen == self._gen
                    if keep:
                        self._idle.append(c)
                if not keep:
                    _close_quietly(c)
            self._slots.release()

    def run(self, sql, args=(), fetch=False):
        sql = sql.replace('?', self.mark) if self.mark != '?' else sql
        for attempt in (1, 2):
            c = None
            try:
                with self.connection() as c:
                    cur = c.cursor()
                    cur.execute(sql, args)
                    rows = cur.fetchall() if fetch else None
            except DatabaseError:
                raise
            except Exception as exc:
                if not _unreachable(exc) and not getattr(c, 'closed', False):
                    raise DatabaseError(f'{self.describe()}: {exc}') from exc
                # A dropped connection (a restart, a failover): the pool threw it away, so the
                # second try opens a new one. Once.
                if attempt == 1:
                    continue
                raise self._mark_down(exc) from exc
            if self.down:
                self._mark_up()
            return rows
        return None

    # ── documents ──

    def get(self, key):
        text = self.get_text(key)
        return text if text is _MISSING else json.loads(text)

    def get_text(self, key):
        """The document as stored (JSON text), or _MISSING."""
        try:
            rows = self.run('SELECT body, updated_at FROM floorbit_documents WHERE doc_key = ?', (key,), fetch=True)
        except DatabaseUnavailable:
            if key in self._docs:
                return self._docs[key][0]
            raise
        if not rows:
            self._docs.pop(key, None)
            return _MISSING
        self._docs[key] = (rows[0][0], rows[0][1])
        return rows[0][0]

    def updated_at(self, key):
        try:
            rows = self.run('SELECT updated_at FROM floorbit_documents WHERE doc_key = ?', (key,), fetch=True)
        except DatabaseUnavailable:
            # The copy's time: caches that compare it see no change, which is true for what they can read.
            return self._docs[key][1] if key in self._docs else None
        return rows[0][0] if rows else None

    def put(self, key, body):
        # Strictly increasing in this process, so two writes in one clock tick still read as a change.
        with self._lock:
            now = self._last_put = max(time.time(), getattr(self, '_last_put', 0) + 1e-6)
        if self.kind == 'sqlite':
            self.run('INSERT INTO floorbit_documents (doc_key, body, updated_at) VALUES (?, ?, ?) '
                     'ON CONFLICT(doc_key) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at',
                     (key, body, now))
        else:
            self.run('INSERT INTO floorbit_documents (doc_key, body, updated_at) VALUES (?, ?, ?) '
                     'ON CONFLICT (doc_key) DO UPDATE SET body = EXCLUDED.body, updated_at = EXCLUDED.updated_at',
                     (key, body, now))
        self._docs[key] = (body, now)
        for prefix, known in self._keys.items():
            if key.startswith(prefix) and key not in known:
                known.append(key)

    def delete(self, key):
        found = self.run('SELECT 1 FROM floorbit_documents WHERE doc_key = ?', (key,), fetch=True)
        self.run('DELETE FROM floorbit_documents WHERE doc_key = ?', (key,))
        self._docs.pop(key, None)
        self._keys.clear()
        return bool(found)

    def keys(self, prefix):
        like = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        try:
            rows = self.run("SELECT doc_key FROM floorbit_documents WHERE doc_key LIKE ? ESCAPE '\\'",
                            (like,), fetch=True)
        except DatabaseUnavailable:
            if prefix in self._keys:
                return list(self._keys[prefix])
            raise
        self._keys[prefix] = [r[0] for r in rows]
        return list(self._keys[prefix])

    # ── append-only logs (floorbit/journal.py) ──

    def log_append(self, key, line):
        self.run('INSERT INTO floorbit_log (log_key, line) VALUES (?, ?)', (key, line))

    def log_lines(self, key):
        rows = self.run('SELECT line FROM floorbit_log WHERE log_key = ? ORDER BY id', (key,), fetch=True)
        return [r[0] for r in rows]

    def log_size(self, key):
        rows = self.run('SELECT COALESCE(SUM(LENGTH(line)), 0) FROM floorbit_log WHERE log_key = ?', (key,), fetch=True)
        return int(rows[0][0] or 0)

    def log_replace(self, key, lines):
        """The log becomes ``lines``, in one transaction: a crash keeps the old one whole."""
        mark = self.mark
        try:
            with self.connection() as c:     # held for the whole transaction
                cur = c.cursor()
                cur.execute('BEGIN IMMEDIATE' if self.kind == 'sqlite' else 'BEGIN')
                try:
                    cur.execute(f'DELETE FROM floorbit_log WHERE log_key = {mark}', (key,))
                    if lines:
                        cur.executemany(f'INSERT INTO floorbit_log (log_key, line) VALUES ({mark}, {mark})',
                                        [(key, line) for line in lines])
                    cur.execute('COMMIT')
                except Exception:
                    cur.execute('ROLLBACK')
                    raise
        except DatabaseError:
            raise
        except Exception as exc:
            if _unreachable(exc):
                raise self._mark_down(exc) from exc
            raise DatabaseError(f'{self.describe()}: {exc}') from exc

    def close(self):
        """Close the idle connections; ones in use are closed when they come back, so none
        opened before the close is handed out again."""
        with self._lock:
            self._gen += 1
            idle, self._idle = self._idle, []
        for c in idle:
            _close_quietly(c)


_MISSING = object()


def _close_quietly(c):
    with suppress(Exception):  # already gone, or the driver can't say goodbye: drop it either way
        c.close()


def migrate(db, conn):
    """Bring the schema up to date. Returns the steps it ran. Two processes starting at once (the
    web app and the flow collector) take turns: SQLite's write lock, a Postgres advisory lock."""
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS floorbit_schema (version INTEGER PRIMARY KEY, applied_at DOUBLE PRECISION)')
    mark = db.mark
    ran = []
    if db.kind == 'postgres':
        cur.execute('SELECT pg_advisory_lock(46400)')
    try:
        # One transaction for all the steps: a step that fails leaves nothing of itself behind.
        cur.execute('BEGIN IMMEDIATE' if db.kind == 'sqlite' else 'BEGIN')
        try:
            cur.execute('SELECT version FROM floorbit_schema')
            done = {r[0] for r in cur.fetchall()}
            for version, statement in enumerate(MIGRATIONS, start=1):
                if version in done:
                    continue
                cur.execute(statement[db.kind] if isinstance(statement, dict) else statement)
                cur.execute(f'INSERT INTO floorbit_schema (version, applied_at) VALUES ({mark}, {mark})',
                            (version, time.time()))
                ran.append(version)
            cur.execute('COMMIT')
        except Exception:
            cur.execute('ROLLBACK')
            raise
    finally:
        if db.kind == 'postgres':
            cur.execute('SELECT pg_advisory_unlock(46400)')
    return ran


_backend = None
_backend_for = None
_backend_lock = threading.Lock()


def state_root():
    from .store import DATA_FILE
    return os.path.dirname(os.path.abspath(DATA_FILE))


def backend():
    """Files, or the database ``FLOORBIT_DATABASE_URL`` names (made once per URL)."""
    global _backend, _backend_for
    url = (os.environ.get(ENV) or '').strip()
    root = state_root()
    if _backend is None or _backend_for != (url, root):
        with _backend_lock:
            if _backend is None or _backend_for != (url, root):
                if _backend is not None and hasattr(_backend, 'close'):
                    _backend.close()
                _backend = Sql(url, root) if url else Files(root)
                _backend_for = (url, root)
    return _backend


def key_for(path, root=None):
    """A document's key: its path under the state folder, with forward slashes."""
    root = root or state_root()
    full = os.path.abspath(path)
    rel = os.path.relpath(full, root)
    if rel.startswith('..'):
        return full.replace(os.sep, '/')     # outside the state folder: the whole path
    return rel.replace(os.sep, '/')


def wait_until_ready(seconds=None):
    """At start: a database container may come up after Floorbit, so wait for it a little
    (``FLOORBIT_DATABASE_WAIT``, default 10 s). If it still doesn't answer, start anyway: the
    pages, the live status and the big screens work without it, saving waits until it is back,
    and ``watch`` keeps trying (docs/database.md)."""
    if seconds is None:
        seconds = float(os.environ.get('FLOORBIT_DATABASE_WAIT') or 10)
    deadline = time.monotonic() + seconds
    while True:
        out = status()
        if out['ok'] or time.monotonic() >= deadline:
            return out
        time.sleep(min(2.0, max(0.1, deadline - time.monotonic())))


def status():
    """For Settings, the health check and the banner: which store, whether it answers, and
    since when it doesn't."""
    b = backend()
    out = {'kind': b.kind, 'where': b.describe(), 'ok': True}
    if b.kind == 'files':
        return out
    try:
        b.run('SELECT 1', fetch=True)
    except DatabaseError as exc:
        out.update(ok=False, error=str(exc))
    down = b.down
    if down:
        out.update(ok=False, since=down['since'], error=out.get('error') or down['error'],
                   retry_in=max(0, round(down['next_try'] - time.monotonic())))
    return out


def available():
    """False while the database doesn't answer, without asking it (cheap, for every request)."""
    b = backend()
    return b.kind == 'files' or b.down is None


_watch_started = False


def watch():
    """Ask the database now and then in the background: soon after it went away (with longer
    waits each time, ``RETRY_*``), every ``PROBE_EVERY`` seconds while it answers. So Floorbit
    notices both on its own, without waiting for someone to load a page."""
    global _watch_started
    if _watch_started or backend().kind == 'files':
        return
    _watch_started = True

    def loop():
        while True:
            b = backend()
            down = getattr(b, 'down', None)    # None too when the store moved to files
            time.sleep(max(0.2, down['next_try'] - time.monotonic()) if down else PROBE_EVERY)
            try:
                status()
            except Exception as exc:  # noqa: BLE001 - the watch itself must never stop
                print(f'[store] Database watch: {exc}', flush=True)

    threading.Thread(target=loop, name='floorbit-db-watch', daemon=True).start()
