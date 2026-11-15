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

ENV = 'FLOORBIT_DATABASE_URL'

# Plain SQL both databases take. Add a step at the end; never change one that has shipped.
MIGRATIONS = (
    """CREATE TABLE floorbit_documents (
        doc_key VARCHAR(512) PRIMARY KEY,
        body TEXT NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL
    )""",
)


class DatabaseError(RuntimeError):
    pass


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


class Sql:
    """SQLite or Postgres: one table of documents. ``connect()`` gives a DB-API connection."""

    def __init__(self, url, root):
        self.url, self.root = url, root
        self._local = threading.local()
        self._lock = threading.Lock()
        self._ready = False
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
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=10000')
            return conn
        try:
            import psycopg
        except ImportError as exc:      # the image has it; a bare `pip install -r` might not
            raise DatabaseError('Postgres needs the psycopg package (pip install "psycopg[binary]").') from exc
        return psycopg.connect(self.url, autocommit=True, connect_timeout=10)

    def conn(self):
        """This thread's connection, opened (and the schema brought up to date) on first use."""
        c = getattr(self._local, 'conn', None)
        if c is None:
            try:
                c = self._connect()
            except DatabaseError:
                raise
            except Exception as exc:  # the driver's own error types differ
                raise DatabaseError(f'Cannot open the database {self.describe()}: {exc}') from exc
            self._local.conn = c
            if not self._ready:
                with self._lock:
                    if not self._ready:
                        migrate(self, c)
                        self._ready = True
        return c

    def run(self, sql, args=(), fetch=False):
        sql = sql.replace('?', self.mark) if self.mark != '?' else sql
        for attempt in (1, 2):
            c = self.conn()
            try:
                cur = c.cursor()
                cur.execute(sql, args)
                return cur.fetchall() if fetch else None
            except Exception as exc:
                # A dropped Postgres connection (a restart, a failover): open a new one, once.
                if self.kind == 'postgres' and attempt == 1 and getattr(c, 'closed', False):
                    self._local.conn = None
                    continue
                raise DatabaseError(f'{self.describe()}: {exc}') from exc
        return None

    # ── documents ──

    def get(self, key):
        rows = self.run('SELECT body FROM floorbit_documents WHERE doc_key = ?', (key,), fetch=True)
        return json.loads(rows[0][0]) if rows else _MISSING

    def updated_at(self, key):
        rows = self.run('SELECT updated_at FROM floorbit_documents WHERE doc_key = ?', (key,), fetch=True)
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

    def delete(self, key):
        found = self.run('SELECT 1 FROM floorbit_documents WHERE doc_key = ?', (key,), fetch=True)
        self.run('DELETE FROM floorbit_documents WHERE doc_key = ?', (key,))
        return bool(found)

    def keys(self, prefix):
        like = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        rows = self.run("SELECT doc_key FROM floorbit_documents WHERE doc_key LIKE ? ESCAPE '\\'", (like,), fetch=True)
        return [r[0] for r in rows]

    def close(self):
        c = getattr(self._local, 'conn', None)
        if c is not None:
            c.close()
            self._local.conn = None


_MISSING = object()


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
                cur.execute(statement)
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
    (``FLOORBIT_DATABASE_WAIT``, default 30 s), then stop with a clear message instead of serving
    pages that can't save anything."""
    if seconds is None:
        seconds = float(os.environ.get('FLOORBIT_DATABASE_WAIT') or 30)
    deadline = time.monotonic() + seconds
    while True:
        out = status()
        if out['ok']:
            return out
        if time.monotonic() >= deadline:
            raise SystemExit(f"[store] {out['where']} doesn't answer: {out.get('error')}")
        time.sleep(2)


def status():
    """For Settings and the health check: which store, and whether it answers."""
    b = backend()
    out = {'kind': b.kind, 'where': b.describe()}
    if b.kind != 'files':
        try:
            b.run('SELECT 1', fetch=True)
            out['ok'] = True
        except DatabaseError as exc:
            out.update(ok=False, error=str(exc))
    else:
        out['ok'] = True
    return out
