"""What the leader's polling loops know, for the other workers and pods (issue #1417).

With the cluster on (``FLOORBIT_CLUSTER``, floorbit/cluster.py) every gunicorn worker is a pod of
its own. A loop that asks LibreNMS or the agent would otherwise ask once per worker, and each
worker's pages would show what its own copy last saw. So only the leader polls. After each poll
the loop puts its read side here (``put``), and the other pods' pages read it back (``get``),
at most ``REREAD`` seconds old.

A "poll now" button on a pod that doesn't lead asks the leader to run it (``ask``); the loop
registers what it answers with ``answer``.

A pod that takes the lead starts from what the old leader put here, so a switch that went down
before the handover is still down, not a fresh baseline.

Without the cluster there is one process: nothing is written, ``get`` answers ``default`` and the
loops keep their state in memory as before.
"""
import json
import threading
import time

KEY = 'floorbit:state:'
PREFIX = 'leader.'          # calls for the leader's loops, through cluster.forward
TTL = 15 * 60               # a leader gone this long leaves nothing behind
REREAD = 2                  # seconds a pod keeps what it read

_lock = threading.Lock()
_read = {}                  # name -> (when read, value)
_answers = {}               # call name -> function(*args) run on the leader
_warned = set()


def _cluster():
    from . import cluster
    return cluster.current


def follower():
    """True when another pod polls and this one reads what it shares."""
    c = _cluster()
    return c is not None and not c.leading()


def _warn(what, exc):
    if what not in _warned:
        _warned.add(what)
        print(f'[cluster] could not share {what}: {exc}')


def put(name, value):
    """The leader's latest read side of one loop, for the other pods. Nothing without the cluster."""
    c = _cluster()
    if c is None:
        return
    try:
        c.bus.set(KEY + name, json.dumps(value, default=str), TTL)
        _warned.discard(name)
    except Exception as exc:  # noqa: BLE001  # the leader's own pages still have it
        _warn(name, exc)


def get(name, default=None, now=None):
    """What the leader last put for ``name``; ``default`` without the cluster or before a first put."""
    c = _cluster()
    if c is None:
        return default
    now = time.time() if now is None else now
    with _lock:
        hit = _read.get(name)
    if hit and 0 <= now - hit[0] < REREAD:
        return hit[1]
    try:
        raw = c.bus.get(KEY + name)
        value = json.loads(raw) if raw else default
    except Exception:  # noqa: BLE001  # Valkey away: what this pod read last, else nothing
        value = hit[1] if hit else default
    with _lock:
        _read[name] = (now, value)
    return value


def answer(name, fn):
    """Let the other pods ask the leader for ``fn`` (a loop's "poll now")."""
    _answers[name] = fn


def ask(name, *args, timeout=30):
    """Run ``name`` on the leader and return its answer; here when this pod leads or there is no
    cluster. Raises RuntimeError when the leader doesn't answer."""
    c = _cluster()
    if c is None or c.leading():
        return _answers[name](*args)
    pod = c.leader_pod()
    if not pod:
        raise RuntimeError('No Floorbit pod is leading right now. Try again in a moment.')
    reply = c.forward(pod, PREFIX + name, list(args), None, timeout)
    if reply is None:
        raise RuntimeError('The leading Floorbit pod did not answer. Try again.')
    if not reply.get('ok'):
        raise RuntimeError(reply.get('error') or 'The leading Floorbit pod could not do it.')
    return reply.get('result')


def serve(method, args, targets=None, timeout=None):
    """A call from another pod (floorbit/cluster.py hands calls named ``leader.*`` here)."""
    fn = _answers.get(str(method)[len(PREFIX):])
    if fn is None:
        raise ValueError('Unknown leader request.')
    return fn(*(args or []))
