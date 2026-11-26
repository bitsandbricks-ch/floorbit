"""One disk budget for everything a local agent keeps on its disk (#1485).

Raw flows, the buffer for while Floorbit is out of reach, and any plugin's files on the agent
register here as a *kind*. ``enforce()`` adds them all up and, past the budget, removes the oldest
files first, whichever kind they belong to: the newest data is the one an incident needs, and a
full disk must never stop the agent from collecting. The newest file of each kind always stays (it
is the one being written).

The budget is ``FLOORBIT_AGENT_DISK_BUDGET_MB``, set on the agent's page in Floorbit (agent_settings)
and read again on every pass, so a change applies without a restart. 0 or unset is automatic: half
of what the agent's volume could hold for it (its free space plus what the kinds already use).

``clean()`` is the hosted side: what an agent reports, checked before the agent page shows it.
"""
import contextlib
import fnmatch
import os
import threading
import time

ENV = 'FLOORBIT_AGENT_DISK_BUDGET_MB'
AUTO_SHARE = 0.5
MB = 1024 * 1024
MAX_KINDS = 16


class Folder:
    """A kind whose data is the files in one folder that match ``pattern``, oldest by mtime."""

    def __init__(self, path, pattern='*'):
        self.path = path
        self.pattern = pattern

    def files(self):
        """[(name, mtime, size)] of the kind's files."""
        out = []
        try:
            names = os.listdir(self.path)
        except OSError:
            return out
        for name in names:
            if not fnmatch.fnmatch(name, self.pattern):
                continue
            try:
                st = os.stat(os.path.join(self.path, name))
            except OSError:
                continue
            out.append((name, st.st_mtime, st.st_size))
        return out

    def remove(self, name):
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(self.path, name))


_kinds = {}
_dropped = {}
_lock = threading.Lock()
_last = {}


def register(name, kind):
    """Count ``kind`` (anything with ``path``, ``files()`` and ``remove(name)``, like Folder) as
    ``name``. Registering a name again replaces it."""
    with _lock:
        _kinds[name] = kind
        _dropped.setdefault(name, 0)


def unregister(name):
    with _lock:
        _kinds.pop(name, None)


def _free(paths):
    free = None
    for path in paths:
        while path and not os.path.isdir(path):
            path = os.path.dirname(path)
        try:
            st = os.statvfs(path or '.')
        except (OSError, AttributeError):
            continue
        avail = st.f_bavail * st.f_frsize
        free = avail if free is None else min(free, avail)
    return free


def budget(used, paths, env=None):
    """(bytes, automatic) for the data the kinds use now."""
    env = os.environ if env is None else env
    try:
        mb = int(str(env.get(ENV) or '0').strip())
    except ValueError:
        mb = 0
    if mb > 0:
        return mb * MB, False
    free = _free(paths)
    if free is None:
        return None, True
    return int((free + used) * AUTO_SHARE), True


def enforce(now=None, env=None):
    """Remove the oldest files past the budget. Returns the report (see ``report``)."""
    now = time.time() if now is None else now
    with _lock:
        kinds = dict(_kinds)
    listed = {name: sorted(kind.files(), key=lambda f: (f[1], f[0])) for name, kind in kinds.items()}
    used = sum(size for files in listed.values() for _n, _t, size in files)
    limit, auto = budget(used, [k.path for k in kinds.values()], env)
    if limit is not None and used > limit:
        # Every file but each kind's newest, oldest first across the kinds.
        candidates = sorted((t, kind, n, size) for kind, files in listed.items() for n, t, size in files[:-1])
        for _t, kind, n, size in candidates:
            if used <= limit:
                break
            try:
                kinds[kind].remove(n)
            except OSError:
                continue
            used -= size
            listed[kind] = [f for f in listed[kind] if f[0] != n]
            with _lock:
                _dropped[kind] = _dropped.get(kind, 0) + 1
    out = {'budget': limit, 'auto': auto, 'used': used, 'kinds': {}}
    for kind, files in listed.items():
        oldest = files[0][1] if files else None
        out['kinds'][kind] = {'bytes': sum(f[2] for f in files), 'files': len(files),
                              'hours': round(max(0.0, now - oldest) / 3600, 1) if oldest else 0,
                              'dropped': _dropped.get(kind, 0)}
    with _lock:
        _last.clear()
        _last.update(out)
    return out


def report():
    """The last pass's numbers, for the agent's report to Floorbit; {} before the first."""
    with _lock:
        return dict(_last)


# ── the hosted side ───────────────────────────────────────────────────────────────────────────

def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def clean(raw):
    """An agent's ``disk`` report, or None. What an agent sends is not trusted: numbers only,
    short kind names, a few of them."""
    if not isinstance(raw, dict) or not isinstance(raw.get('kinds'), dict):
        return None
    out = {'auto': raw.get('auto') is True, 'kinds': {}}
    for key in ('budget', 'used'):
        if _number(raw.get(key)):
            out[key] = raw[key]
    for name, row in list(raw['kinds'].items())[:MAX_KINDS]:
        if not isinstance(name, str) or not name or len(name) > 40 or not isinstance(row, dict):
            continue
        out['kinds'][name] = {k: row[k] for k in ('bytes', 'files', 'hours', 'dropped') if _number(row.get(k))}
    return out
