"""A terminal in the browser for one switch (issue #95). See docs/terminal.md.

The browser opens a session with the tech's own switch login, sends what they type and asks for
the output with a long poll (one gunicorn worker keeps the sessions in memory). The login is
used to open the one SSH connection and dropped: never stored, logged or cached.

Every line the tech sends goes to the audit log, as typed, with the switch: the session's record.
A line typed while the switch asks for a password is logged as hidden. What the switch prints
is not logged: it can name MACs and IPs.

Sessions end when the tech closes them, after ``TERMINAL_IDLE_MINUTES`` (10) without input, after
``TERMINAL_MAX_MINUTES`` (60) in all, or when the switch hangs up.
"""
import contextlib
import re
import secrets
import threading
import time

from integrations import config

from . import audit, ports
from .plugins import PluginError
from .store import load_data

MAX_SESSIONS = 10           # in all, so a stuck browser can't open connections without end
MAX_PER_ACCOUNT = 3
MAX_INPUT = 4096            # characters per input request
BUFFER = 256 * 1024         # output kept for the browser to read
POLL_SECONDS = 20
SECRET_PROMPT = re.compile(r'(password|passphrase|secret)[^\n]{0,20}:\s*$', re.I)

_lock = threading.Lock()
_sessions = {}


class TerminalError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def idle_seconds():
    return config.get_int('TERMINAL_IDLE_MINUTES', 10, minimum=1) * 60


def max_seconds():
    return config.get_int('TERMINAL_MAX_MINUTES', 60, minimum=1) * 60


def plugin(registry):
    spec = ports.plugin(registry)
    if not spec:
        return None
    cls = spec.plugin_class()
    return spec if cls is not None and hasattr(cls, 'open_shell') else None


class Session:
    def __init__(self, sid, account, switch, shell):
        self.id, self.account, self.switch, self.shell = sid, account, switch, shell
        self.opened = self.last_input = time.time()
        self.out = ''              # output not yet trimmed away
        self.offset = 0            # characters dropped from the front of ``out``
        self.line = ''             # what the tech typed since the last Enter
        self.closed = None         # why it ended
        self.cond = threading.Condition()
        self.reader = threading.Thread(target=self._read, name=f'terminal-{switch}', daemon=True)
        self.reader.start()

    def _read(self):
        while not self.closed:
            try:
                data = self.shell.recv()
            except Exception:  # noqa: BLE001 - a dead connection ends the session
                data = None
            if data is None:
                self.end('The switch closed the connection.')
                return
            if data:
                with self.cond:
                    self.out += data
                    if len(self.out) > BUFFER:
                        cut = len(self.out) - BUFFER
                        self.out, self.offset = self.out[cut:], self.offset + cut
                    self.cond.notify_all()
            else:
                time.sleep(0.03)

    def end(self, why):
        with self.cond:
            if self.closed:
                return
            self.closed = why
            self.cond.notify_all()
        with contextlib.suppress(Exception):
            self.shell.close()
        with _lock:
            _sessions.pop(self.id, None)
        audit.record('terminal', 'Closed terminal', user=self.account,
                     target=f'{self.switch}: {why}'[:120])

    def write(self, data):
        if self.closed:
            raise TerminalError(self.closed, 410)
        if not isinstance(data, str) or len(data) > MAX_INPUT:
            raise TerminalError('Bad input.')
        self.last_input = time.time()
        self._record(data)
        self.shell.send(data)

    def _record(self, data):
        """Collect the typed line and send it to the audit log on Enter."""
        for ch in data:
            if ch in '\r\n':
                with self.cond:
                    hidden = bool(SECRET_PROMPT.search(self.out[-200:]))
                if self.line.strip() or hidden:
                    text = '(hidden: the switch asked for a password)' if hidden else self.line.strip()
                    audit.record('terminal', 'Typed', user=self.account, target=f'{self.switch}: {text}'[:120])
                self.line = ''
            elif ch in '\x7f\b':
                self.line = self.line[:-1]
            elif ch == '\x03' or ch == '\x15':   # Ctrl-C, Ctrl-U: the line is gone
                self.line = ''
            elif ch >= ' ':
                self.line = (self.line + ch)[-500:]

    def read(self, after, wait=POLL_SECONDS):
        """Output after character ``after``; waits up to ``wait`` seconds for some."""
        deadline = time.time() + wait
        with self.cond:
            while self.offset + len(self.out) <= after and not self.closed:
                left = deadline - time.time()
                if left <= 0:
                    break
                self.cond.wait(left)
            start = max(after - self.offset, 0)
            return {'data': self.out[start:], 'next': self.offset + len(self.out),
                    'skipped': max(self.offset - after, 0), 'closed': self.closed}


def open_session(registry, account, body):
    spec = plugin(registry)
    if not spec:
        raise TerminalError('No plugin that can open a switch terminal is on. An admin turns on SSH port '
                            'actions under Settings > Plugins.', 409)
    prune()
    with _lock:
        mine = [s for s in _sessions.values() if s.account == account]
        if len(_sessions) >= MAX_SESSIONS:
            raise TerminalError('Too many terminals are open. Close one first.', 429)
        if len(mine) >= MAX_PER_ACCOUNT:
            raise TerminalError(f'You have {MAX_PER_ACCOUNT} terminals open. Close one first.', 429)
    try:
        dev = ports._switch(load_data(), body.get('switch'))
    except ports.PortError as exc:
        raise TerminalError(str(exc)) from None
    needs_login = ports.info(registry)['needs_login']
    try:
        login = ports._login(body, needs_login)
    except ports.PortError as exc:
        raise TerminalError(str(exc)) from None
    body.pop('password', None)
    with ports._lock:
        try:
            ports._check_failures(account, time.time())
        except ports.PortError as exc:
            if login:
                login.clear()
            raise TerminalError(str(exc), exc.status) from None
    cols = min(max(int(body.get('cols') or 120), 40), 300)
    rows = min(max(int(body.get('rows') or 32), 10), 120)
    try:
        shell = registry.call(spec, 'open_shell', {'switch': dev['name'], 'host': dev['mgmt_ip'], 'login': login,
                                                   'cols': cols, 'rows': rows})
    except PluginError as exc:
        if needs_login and 'login' in str(exc).lower():
            with ports._lock:
                ports._failures.setdefault(account, []).append(time.time())
        audit.record('terminal', 'Opened terminal: failed', user=account, target=dev['name'], ok=False)
        raise TerminalError(str(exc), 502) from None
    finally:
        if login:
            login.clear()
    with ports._lock:
        ports._failures.pop(account, None)
    session = Session(secrets.token_urlsafe(18), account, dev['name'], shell)
    with _lock:
        _sessions[session.id] = session
    audit.record('terminal', 'Opened terminal', user=account, target=dev['name'])
    return session


def get(sid, account):
    with _lock:
        session = _sessions.get(sid)
    # Someone else's session looks the same as one that doesn't exist.
    if not session or session.account != account:
        raise TerminalError('That terminal is closed.', 404)
    return session


def prune(now=None):
    now = time.time() if now is None else now
    with _lock:
        sessions = list(_sessions.values())
    for s in sessions:
        if now - s.last_input > idle_seconds():
            s.end(f'No input for {idle_seconds() // 60} minutes.')
        elif now - s.opened > max_seconds():
            s.end(f'Open for {max_seconds() // 60} minutes.')


def listing(account):
    prune()
    with _lock:
        return [{'id': s.id, 'switch': s.switch, 'opened': s.opened} for s in _sessions.values()
                if s.account == account]
