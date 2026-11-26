"""Several Floorbit pods behind one address (issue #465). Docs: docs/kubernetes.md.

One pod is the default and needs none of this. With ``FLOORBIT_CLUSTER=redis`` the pods share
Redis (``REDIS_HOST``) for four things that otherwise live in one pod's memory:

- **Live updates.** An event published on one pod reaches the browsers connected to every other
  pod (Redis pub/sub). Python subscribers run only where the event was published.
- **Agent calls.** A local agent holds its link to one pod. A call made on another pod goes to that
  pod through a Redis list and the answer comes back the same way.
- **Switch terminals.** A terminal's SSH connection lives in the pod that opened it; the other pods
  pass its requests there the same way (floorbit/terminal_cluster.py).
- **One leader.** Only the pod holding the leader lease runs the background checks (status
  monitor, port watch, health, security, power, ...) and shares what they saw with the others
  (floorbit/shared_state.py). Their automatic side effects (Discord alerts, webhooks, the event
  timeline, plugin hooks, replay frames) come from there too, so an alert goes out once. Events
  caused by a request still act on the pod that took the request.

The documents and logs are shared through the database (``FLOORBIT_DATABASE_URL``), which several
pods need anyway.

When Redis can't be reached, every pod acts as the leader: a duplicate alert is better than none.
"""
import contextlib
import json
import os
import socket
import threading
import time
import uuid

from .vault import VaultError

CHANNEL = 'floorbit:events'
LEADER_KEY = 'floorbit:leader'
AGENTS_KEY = 'floorbit:agents'           # hash: agent id -> {"pod", "at"}
PODS_KEY = 'floorbit:pods'               # hash: pod -> {"at", "leader"}, for the Local agents page
CALLS_KEY = 'floorbit:calls:'            # + pod: calls for the agents connected there
REPLY_KEY = 'floorbit:reply:'            # + call id
LEASE_MS = 20_000                        # the leader renews every RENEW s; a dead one is replaced after this
RENEW = 5
AGENT_FRESH = 60                         # an agent this long unseen on its pod is not there any more
FORWARD_WORKERS = 8


def pod_id():
    """This pod's name: the hostname (the pod name on Kubernetes) and a random part, for two
    processes on one machine."""
    return f'{socket.gethostname()}-{uuid.uuid4().hex[:6]}'


class RedisBus:
    """The few Redis operations the cluster uses. Blocking reads get their own connection."""

    def __init__(self, prefix='', **params):
        import redis
        self._redis = redis
        self.params = params
        self.prefix = prefix      # the hosted tenant's, so tenants can share one Redis
        self.short = redis.Redis(**params, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)
        self.blocking = redis.Redis(**params, decode_responses=True, socket_connect_timeout=5)

    def lease(self, key, value, ms):
        """Take or keep a lease; returns who holds it now."""
        key = self.prefix + key
        self.short.set(key, value, nx=True, px=ms)
        holder = self.short.get(key)
        if holder == value:
            # Only lengthen it: a SET here could overwrite another pod that took the lease since the
            # GET, and both would lead. PEXPIRE on its lease just gives that pod a little longer.
            self.short.pexpire(key, ms)
        return holder

    def publish(self, channel, message):
        self.short.publish(self.prefix + channel, message)

    def listen(self, channel, handler, stop, on_resume=None):
        paused = False
        while not stop.is_set():
            try:
                pubsub = self.blocking.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(self.prefix + channel)
                if paused:
                    paused = False
                    print('[cluster] live updates from other pods flow again')
                    if on_resume:
                        on_resume()
                while not stop.is_set():
                    msg = pubsub.get_message(timeout=1.0)
                    if msg and msg.get('type') == 'message':
                        handler(msg['data'])
            except self._redis.RedisError as exc:
                if not paused:
                    print(f'[cluster] live updates from other pods paused: {exc}')
                paused = True
                stop.wait(2)

    def push(self, key, message, ttl=None):
        key = self.prefix + key
        self.short.rpush(key, message)
        if ttl:
            self.short.expire(key, ttl)

    def pop(self, key, timeout):
        got = self.blocking.blpop([self.prefix + key], timeout=max(1, int(timeout)))
        return got[1] if got else None

    def hset(self, key, field, value):
        self.short.hset(self.prefix + key, field, value)

    def hgetall(self, key):
        return self.short.hgetall(self.prefix + key) or {}

    def hget(self, key, field):
        return self.short.hget(self.prefix + key, field)

    def hdel(self, key, field):
        self.short.hdel(self.prefix + key, field)

    def set(self, key, value, ttl):
        self.short.set(self.prefix + key, value, ex=int(ttl))

    def get(self, key):
        return self.short.get(self.prefix + key)


class Cluster:
    """This pod's part. ``deliver(event)`` hands an event from another pod to local browsers;
    ``run_call(method, args, targets, timeout)`` asks an agent connected here."""

    def __init__(self, bus, pod=None, deliver=None, run_call=None, log=print):
        self.bus, self.pod, self.log = bus, pod or pod_id(), log
        self.deliver, self.run_call = deliver, run_call
        self._leading = True
        self._stop = threading.Event()
        self._threads = []
        self._seen_sent = {}

    # ── leader ──

    def renew(self):
        try:
            holder = self.bus.lease(LEADER_KEY, self.pod, LEASE_MS)
        except Exception as exc:  # noqa: BLE001  # Redis away: everyone acts, see the module doc
            if not self._leading:
                self.log(f'[cluster] Redis unreachable, acting as leader: {exc}')
            self._leading = True
            return True
        was, self._leading = self._leading, holder == self.pod
        if was != self._leading:
            self.log(f'[cluster] {self.pod} {"is now" if self._leading else "is no longer"} the leader')
        with contextlib.suppress(Exception):
            self.bus.hset(PODS_KEY, self.pod, json.dumps({'at': time.time(), 'leader': self._leading}))
        return self._leading

    def pods(self, now=None):
        """``[{"pod", "at", "leader", "me"}]``: the pods that renewed lately, this one first."""
        now = time.time() if now is None else now
        try:
            rows = self.bus.hgetall(PODS_KEY)
        except Exception:  # noqa: BLE001
            rows = {}
        out = []
        for pod, raw in rows.items():
            try:
                row = json.loads(raw)
                at = float(row.get('at') or 0)
            except (TypeError, ValueError, AttributeError):
                continue
            if now - at < LEASE_MS / 1000 * 3:
                out.append({'pod': pod, 'at': at, 'leader': bool(row.get('leader')), 'me': pod == self.pod})
        if not any(p['me'] for p in out):
            out.append({'pod': self.pod, 'at': now, 'leader': self._leading, 'me': True})
        return sorted(out, key=lambda p: (not p['me'], p['pod']))

    def leading(self):
        return self._leading

    def leader_pod(self, now=None):
        """The pod holding the leader lease, as the pods last said; None while nobody does."""
        return next((p['pod'] for p in self.pods(now) if p['leader']), None)

    # ── live updates ──

    def publish(self, event):
        try:
            self.bus.publish(CHANNEL, json.dumps({'pod': self.pod, 'event': event}, default=str))
        except Exception as exc:  # noqa: BLE001  # this pod's browsers still got it
            self.log(f'[cluster] could not pass an event on: {exc}')

    def _heard(self, raw):
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            return
        if msg.get('pod') != self.pod and isinstance(msg.get('event'), dict) and self.deliver:
            self.deliver(msg['event'])

    def _resumed(self):
        # Other pods' changes while Redis was away never reached this pod's browsers.
        from integrations import events
        events.resync_all()

    # ── agent calls ──

    def agent_seen(self, agent_id, now=None):
        """An agent asked this pod for work. Written at most every few seconds per agent."""
        now = time.time() if now is None else now
        if now - self._seen_sent.get(agent_id, 0) < RENEW:
            return
        self._seen_sent[agent_id] = now
        with contextlib.suppress(Exception):
            self.bus.hset(AGENTS_KEY, agent_id, json.dumps({'pod': self.pod, 'at': now}))

    def agent_left(self, agent_id):
        """An agent's link to this pod closed: the other pods stop sending its calls here."""
        self._seen_sent.pop(agent_id, None)
        with contextlib.suppress(Exception):
            row = json.loads(self.bus.hget(AGENTS_KEY, agent_id) or 'null')
            if isinstance(row, dict) and row.get('pod') == self.pod:
                self.bus.hdel(AGENTS_KEY, agent_id)

    def agents_elsewhere(self, now=None):
        """{agent id: pod} for agents connected to other pods."""
        now = time.time() if now is None else now
        try:
            rows = self.bus.hgetall(AGENTS_KEY)
        except Exception:  # noqa: BLE001
            return {}
        out = {}
        for agent_id, raw in rows.items():
            try:
                row = json.loads(raw)
                pod, at = row['pod'], float(row.get('at') or 0)
            except (TypeError, ValueError, KeyError, AttributeError):
                continue                 # another version's row, or garbage: not an agent we can reach
            if pod and pod != self.pod and now - at < AGENT_FRESH:
                out[agent_id] = pod
        return out

    def forward(self, pod, method, args, targets, timeout):
        """Ask ``pod`` to run a call on its agent; returns {"ok", "result", "error"} or None on timeout."""
        call_id = uuid.uuid4().hex
        # Sealed: a switch call carries its login, and Redis is no place for it in the clear.
        body = _seal('cluster-call:' + call_id, {'method': method, 'args': list(args),
                                                 'targets': sorted(targets) if targets else None})
        self.bus.push(CALLS_KEY + pod, json.dumps({'id': call_id, 'sealed': body, 'timeout': timeout,
                                                   'deadline': time.time() + timeout}),
                      ttl=int(timeout) + 30)
        raw = self.bus.pop(REPLY_KEY + call_id, timeout + 2)
        if not raw:
            return None
        reply = json.loads(raw)
        if isinstance(reply, dict) and 'sealed' in reply:
            reply = _open('cluster-reply:' + call_id, reply['sealed'])
        return reply

    def _serve_call(self, raw):
        try:
            call = json.loads(raw)
        except (TypeError, ValueError):
            return
        try:
            left = float(call.get('deadline') or 0) - time.time()
            call_id, timeout = call['id'], float(call['timeout'])
            sealed = 'sealed' in call
            if sealed:
                call.update(_open('cluster-call:' + call_id, call['sealed']))
            method = call['method']
        except (TypeError, ValueError, KeyError, AttributeError, VaultError):
            return                       # not a call this version (or key) understands; its caller times out
        if left <= 0:
            return                       # the caller gave up already
        # A switch terminal this pod holds (floorbit/terminal_cluster.py), a call for the leader's
        # loops (floorbit/shared_state.py), else a call for an agent here.
        from . import shared_state, terminal_cluster
        if str(method).startswith(terminal_cluster.PREFIX):
            run = terminal_cluster.serve
        elif str(method).startswith(shared_state.PREFIX):
            run = shared_state.serve
        else:
            run = self.run_call
        try:
            result = run(method, call.get('args') or [], call.get('targets'), min(left, timeout))
            reply = {'ok': True, 'result': result}
        except Exception as exc:  # noqa: BLE001  # goes back to the caller as the error
            reply = {'ok': False, 'error': str(exc)[:300], 'unavailable': type(exc).__name__ == 'AgentUnavailable'}
        with contextlib.suppress(Exception):
            if sealed:
                reply = {'sealed': _seal('cluster-reply:' + call_id, reply)}
            self.bus.push(REPLY_KEY + call_id, json.dumps(reply, default=str), ttl=60)

    def _take_calls(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=FORWARD_WORKERS, thread_name_prefix='cluster-call') as pool:
            while not self._stop.is_set():
                try:
                    raw = self.bus.pop(CALLS_KEY + self.pod, 5)
                except Exception as exc:  # noqa: BLE001
                    self.log(f'[cluster] cannot take calls from other pods: {exc}')
                    self._stop.wait(2)
                    continue
                if raw:
                    pool.submit(self._serve_call, raw)

    # ── running ──

    def _renew_loop(self):
        while not self._stop.is_set():
            self.renew()
            self._stop.wait(RENEW)

    def start(self):
        for target, name in ((self._renew_loop, 'cluster-leader'),
                             (lambda: self.bus.listen(CHANNEL, self._heard, self._stop, self._resumed),
                              'cluster-events'),
                             (self._take_calls, 'cluster-calls')):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        self.log(f'[cluster] pod {self.pod} joined (Redis)')

    def stop(self):
        self._stop.set()


current = None


def status(now=None):
    """This Floorbit's own availability for the Local agents page: one pod or several, which leads,
    and whether Redis and the database answer."""
    from . import cache, database
    db = database.status()
    out = {'mode': 'single' if current is None else 'redis',
           'database': {'kind': db.get('kind'), 'ok': bool(db.get('ok')), 'since': db.get('since')}}
    try:
        client = cache.get_redis_client()
        out['redis'] = {'ok': client is not None}
    except Exception:  # noqa: BLE001
        out['redis'] = {'ok': False}
    if current is None:
        at = time.time() if now is None else now
        out['pods'] = [{'pod': socket.gethostname(), 'at': at, 'leader': True, 'me': True}]
    else:
        out['pods'] = current.pods(now)
    return out


def leading():
    """Should this pod act on automatic side effects? Always yes with one pod."""
    return current is None or current.leading()


def init(log=print):
    """Join the cluster when FLOORBIT_CLUSTER=redis (or valkey). Returns the Cluster or None."""
    global current
    mode = (os.environ.get('FLOORBIT_CLUSTER') or '').strip().lower()
    if mode in ('', 'off', 'none'):
        return None
    # Valkey speaks the Redis protocol, so both names mean the same shared cache.
    if mode not in ('redis', 'valkey'):
        raise ValueError(f'FLOORBIT_CLUSTER must be "redis", "valkey" or empty, not "{mode}".')
    from integrations import events

    from . import agent_link, cache
    bus = RedisBus(prefix=cache.redis_prefix(), host=cache.REDIS_HOST, port=cache.REDIS_PORT, db=cache.REDIS_DB,
                   password=cache.REDIS_PASSWORD)
    current = Cluster(bus, deliver=events.deliver_local, run_call=agent_link.tunnel.call_here, log=log)
    current.renew()
    current.start()
    return current


def _seal(slot, value):
    from . import vault
    return vault.seal(slot, json.dumps(value, default=str))


def _open(slot, sealed):
    from . import vault
    return json.loads(vault.open_(slot, sealed))
