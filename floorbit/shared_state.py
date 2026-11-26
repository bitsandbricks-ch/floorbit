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


def my_turn(poller):
    """Should this pod's ``poller`` poll now? Only on the leader. The first time after this pod took
    the lead, the poller carries on from what the old leader shared (``take_over``)."""
    from . import cluster
    if not cluster.leading():
        poller._shared_led = False
        return False
    if not getattr(poller, '_shared_led', False):
        poller._shared_led = True
        poller.answer_calls()
        poller.take_over()
    return True


class _View:
    """A poller as the leader last shared it: its shared fields from there, the rest its own."""

    def __init__(self, own, seen):
        self._own, self._seen = own, seen

    def __getattr__(self, name):
        if name in self._own.shared_fields and name in self._seen:
            return self._own.shared_restore(name, self._seen[name])
        return getattr(self._own, name)


class Shared:
    """For a poller whose read side the other pods show. Set ``shared_name`` and ``shared_fields``
    (attributes that survive JSON: dict keys become text, tuples and sets lists), call ``share()``
    at the end of each poll, read through ``view()``, and ask ``poll_now()`` from requests.
    ``leader_calls`` names more methods a request runs on the leader with ``on_leader``."""
    shared_name = None
    shared_fields = ()
    leader_calls = ()

    def answer_calls(self):
        for method in ('poll_once', *self.leader_calls):
            if hasattr(self, method):
                answer(f'{self.shared_name}.{method}', getattr(self, method))

    def share(self):
        # The leader shares after each poll: from now on the other pods' "check now" reaches it.
        self.answer_calls()
        put(self.shared_name, {f: self.shared_dump(f, getattr(self, f)) for f in self.shared_fields})

    def take_over(self):
        seen = get(self.shared_name)
        if isinstance(seen, dict):
            for f in self.shared_fields:
                if f in seen:
                    setattr(self, f, self.shared_restore(f, seen[f]))

    @staticmethod
    def shared_dump(field, value):
        """A field as it goes to Valkey (a subclass flattens dicts with tuple keys)."""
        return _plain(value)

    @staticmethod
    def shared_restore(field, value):
        """A shared field back as the poller keeps it (a subclass turns lists back into sets)."""
        return value

    def view(self):
        if not follower():
            return self
        seen = get(self.shared_name)
        return _View(self, seen if isinstance(seen, dict) else {})

    def poll_now(self, *args):
        """A "check now" from a request: polls on the leader, wherever the request landed."""
        return self.on_leader('poll_once', *args)

    def on_leader(self, method, *args):
        """``method`` run on the leader (here without the cluster); its answer."""
        self.answer_calls()
        try:
            return ask(f'{self.shared_name}.{method}', *args)
        finally:
            with _lock:
                _read.pop(self.shared_name, None)    # show what that poll found, not the last read


def _plain(value):
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    return value
