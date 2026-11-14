"""Floorbit's own log (issue #93): what the app prints ("[syslog] could not prune: ..."), kept in
memory for the Logs page next to the syslog and the audit log. Nothing is written to disk: the
container's log has it all; this is the last ``APP_LOG_LINES`` (2000) lines for the crew.

The app writes its log with ``print("[area] text")`` to stdout and stderr. ``install()`` puts a tee
in front of both, so everything still reaches the container's log as before.
"""
import contextlib
import re
import sys
import threading
import time
from collections import deque

from integrations import config

TAG = re.compile(r'^\[([\w .:-]{1,32})\]\s*(.*)$', re.S)
ERROR = re.compile(r"error|could not|couldn't|can't|failed|traceback|exception", re.I)
WARNING = re.compile(r'warn|retry|retrying|timed out|timeout', re.I)
# The development server's request lines: the access log is not what this page is for.
ACCESS = re.compile(r'" \d{3} (?:\d+|-)$')


class AppLog:
    def __init__(self):
        self._lock = threading.Lock()
        self.lines = deque(maxlen=config.get_int('APP_LOG_LINES', 2000, minimum=100))
        self.next_id = 1
        self._partial = {}

    def add(self, text, stream='stdout', now=None):
        """One printed line. Returns the kept line, or None for blank and access-log lines."""
        text = text.rstrip()
        if not text.strip() or ACCESS.search(text):
            return None
        now = time.time() if now is None else now
        m = TAG.match(text)
        program, message = (m[1], m[2]) if m else (None, text)
        severity = 'err' if ERROR.search(message) else 'warning' if WARNING.search(message) else 'info'
        if stream == 'stderr' and severity == 'info':
            severity = 'notice'
        with self._lock:
            line = {'id': self.next_id, 'ts': now, 'severity': severity, 'device': 'Floorbit', 'program': program,
                    'message': message[:2048], 'port': None, 'seat': None}
            self.next_id += 1
            self.lines.append(line)
        return line

    def write(self, stream, data):
        # print() sends the text and the newline in separate writes: keep the pieces until a line ends.
        buffered = self._partial.get(stream, '') + data
        *done, rest = buffered.split('\n')
        self._partial[stream] = rest[-4096:]
        for text in done:
            self.add(text, stream)

    def search(self, q='', device='', severity='', before=None, limit=200):
        from .syslog import SEVERITIES
        words = [w for w in str(q or '').lower().split() if w]
        worst = SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES) - 1
        with self._lock:
            lines = list(self.lines)
        out = []
        for line in reversed(lines):
            if before is not None and line['id'] >= before:
                continue
            if SEVERITIES.index(line['severity']) > worst:
                continue
            if device and device.lower() != 'floorbit':
                return []
            text = f"{line['program'] or ''} {line['message']}".lower()
            if words and not all(w in text for w in words):
                continue
            out.append(line)
            if len(out) >= limit:
                break
        return out


class _Tee:
    def __init__(self, inner, log, name):
        self._inner, self._log, self._name = inner, log, name

    def write(self, data):
        with contextlib.suppress(Exception):   # the log must never break a print
            self._log.write(self._name, data)
        return self._inner.write(data)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def install(log):
    """Tee stdout and stderr into ``log``. Safe to call twice."""
    for name in ('stdout', 'stderr'):
        stream = getattr(sys, name)
        if not isinstance(stream, _Tee):
            setattr(sys, name, _Tee(stream, log, name))


def init_app_log(app, start_background=True):
    log = AppLog()
    app.extensions['floorbit_app_log'] = log
    # From the start, so the startup lines are in it. Not under pytest: it swaps stdout around
    # each test, and the tests feed the log directly.
    if start_background and 'pytest' not in sys.modules:
        install(log)
    return log
