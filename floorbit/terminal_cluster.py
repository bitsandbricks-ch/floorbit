"""The switch terminal behind several workers or pods (issue #1417). See docs/terminal.md.

A terminal's SSH connection lives in the process that opened it. With ``FLOORBIT_CLUSTER`` on, the
browser's next request can land on another worker or pod, so every process lists its open
terminals in Valkey (``TERMINALS_KEY``: id -> pod, account, switch, opened), and a process that
doesn't hold the terminal passes the request to the one that does, over the same sealed call queue
the agent calls use (floorbit/cluster.py). Typed input can be a password, so it never crosses
Valkey in the clear.

Without the cluster, none of this runs: one process holds every terminal.
"""
import contextlib
import json

TERMINALS_KEY = 'floorbit:terminals'
PREFIX = 'terminal.'
SLACK = 5            # seconds a forwarded call may take beyond the work itself


def _cluster():
    from . import cluster
    return cluster.current


def announce(session):
    """A terminal opened here: other processes send its requests here."""
    here = _cluster()
    if here is None:
        return
    with contextlib.suppress(Exception):   # Valkey away: the terminal still works through this process
        here.bus.hset(TERMINALS_KEY, session.id, json.dumps({
            'pod': here.pod, 'account': session.account, 'switch': session.switch, 'opened': session.opened}))


def forget(sid):
    here = _cluster()
    if here is None:
        return
    with contextlib.suppress(Exception):
        here.bus.hdel(TERMINALS_KEY, sid)


def elsewhere():
    """{id: row} for the terminals other live processes hold. Rows of a process that stopped are
    dropped: its SSH connections went with it."""
    here = _cluster()
    if here is None:
        return {}
    try:
        rows = here.bus.hgetall(TERMINALS_KEY)
    except Exception:  # noqa: BLE001
        return {}
    alive = {p['pod'] for p in here.pods()}
    out = {}
    for sid, raw in rows.items():
        try:
            row = json.loads(raw)
            pod, account = row['pod'], row['account']
        except (TypeError, ValueError, KeyError):
            continue
        if pod == here.pod:
            continue
        if pod not in alive:
            forget(sid)
            continue
        out[sid] = {'pod': pod, 'account': account, 'switch': row.get('switch') or '',
                    'opened': row.get('opened') or 0}
    return out


class RemoteSession:
    """A terminal another process holds: the same methods as terminal.Session, each one a call to
    that process."""

    def __init__(self, sid, row):
        self.id, self.pod = sid, row['pod']
        self.account, self.switch, self.opened = row['account'], row['switch'], row['opened']

    def _ask(self, op, args, timeout):
        from .terminal import TerminalError
        reply = _cluster().forward(self.pod, PREFIX + op, [self.id, self.account, *args], None, timeout)
        if reply is None:
            raise TerminalError('The server holding this terminal did not answer. Try again.', 504)
        if not reply.get('ok'):
            raise TerminalError(reply.get('error') or 'The terminal failed.', 502)
        result = reply.get('result') or {}
        if 'error' in result:
            raise TerminalError(result['error'], int(result.get('status') or 400))
        return result.get('value')

    def read(self, after, wait):
        return self._ask('read', [after, wait], wait + SLACK)

    def write(self, data):
        self._ask('write', [data], SLACK)

    def resize(self, cols, rows):
        self._ask('resize', [cols, rows], SLACK * 2)

    def end(self, why):
        self._ask('end', [why], SLACK)


def find(sid, account):
    """The terminal ``sid`` of ``account`` held by another process, or None."""
    row = elsewhere().get(sid)
    if not row or row['account'] != account:
        return None
    return RemoteSession(sid, row)


def serve(method, args, targets=None, timeout=None):
    """Run a request another process passed on, on a terminal this one holds. A refusal comes
    back as {"error", "status"}, so the browser gets the same answer as from this process."""
    from . import terminal
    from .plugins import PluginError
    op = method[len(PREFIX):]
    sid, account, *rest = args
    try:
        session = terminal.get(sid, account, here_only=True)
        if op == 'read':
            after, wait = rest
            return {'value': session.read(int(after), min(float(wait), terminal.POLL_SECONDS))}
        if op == 'write':
            session.write(rest[0])
        elif op == 'resize':
            session.resize(int(rest[0]), int(rest[1]))
        elif op == 'end':
            session.end(str(rest[0]))
        else:
            return {'error': 'Unknown terminal request.', 'status': 400}
        return {'value': None}
    except terminal.TerminalError as exc:
        return {'error': str(exc), 'status': exc.status}
    except PluginError as exc:
        return {'error': str(exc), 'status': 502}
