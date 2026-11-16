"""Several Floorbit pods behind one address (issue #465). Docs: docs/kubernetes.md.

One pod is the default and needs none of this. With ``FLOORBIT_CLUSTER=redis`` the pods share
Redis (``REDIS_HOST``) for three things that otherwise live in one pod's memory:

- **Live updates.** An event published on one pod reaches the browsers connected to every other
  pod (Redis pub/sub). Python subscribers run only where the event was published.
- **Agent calls.** A local agent holds its link to one pod. A call made on another pod goes to that
  pod through a Redis list and the answer comes back the same way.
- **One leader.** Automatic side effects (Discord alerts, webhooks, the event timeline, plugin
  hooks, replay frames) come from background loops that run on every pod. Only the pod holding the
  leader lease acts on them, so an alert goes out once. Events caused by a request still act on
  the pod that took the request.

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

CHANNEL = 'floorbit:events'
LEADER_KEY = 'floorbit:leader'
AGENTS_KEY = 'floorbit:agents'           # hash: agent id -> {"pod", "at"}
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

    def __init__(self, **params):
        import redis
        self._redis = redis
        self.params = params
        self.short = redis.Redis(**params, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)
        self.blocking = redis.Redis(**params, decode_responses=True, socket_connect_timeout=5)

    def lease(self, key, value, ms):
        """Take or keep a lease; returns who holds it now."""
        self.short.set(key, value, nx=True, px=ms)
        holder = self.short.get(key)
        if holder == value:
            # Only lengthen it: a SET here could overwrite another pod that took the lease since the
            # GET, and both would lead. PEXPIRE on its lease just gives that pod a little longer.
            self.short.pexpire(key, ms)
        return holder

    def publish(self, channel, message):
        self.short.publish(channel, message)

    def listen(self, channel, handler, stop):
        while not stop.is_set():
            try:
                pubsub = self.blocking.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(channel)
                while not stop.is_set():
                    msg = pubsub.get_message(timeout=1.0)
                    if msg and msg.get('type') == 'message':
                        handler(msg['data'])
            except self._redis.RedisError as exc:
                print(f'[cluster] live updates from other pods paused: {exc}')
                stop.wait(2)

    def push(self, key, message, ttl=None):
        self.short.rpush(key, message)
        if ttl:
            self.short.expire(key, ttl)

    def pop(self, key, timeout):
        got = self.blocking.blpop([key], timeout=max(1, int(timeout)))
        return got[1] if got else None

    def hset(self, key, field, value):
        self.short.hset(key, field, value)

    def hgetall(self, key):
        return self.short.hgetall(key) or {}


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
        return self._leading

    def leading(self):
        return self._leading

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

    # ── agent calls ──

    def agent_seen(self, agent_id, now=None):
        """An agent asked this pod for work. Written at most every few seconds per agent."""
        now = time.time() if now is None else now
        if now - self._seen_sent.get(agent_id, 0) < RENEW:
            return
        self._seen_sent[agent_id] = now
        with contextlib.suppress(Exception):
            self.bus.hset(AGENTS_KEY, agent_id, json.dumps({'pod': self.pod, 'at': now}))

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
        self.bus.push(CALLS_KEY + pod, json.dumps({'id': call_id, 'method': method, 'args': list(args),
                                                   'targets': sorted(targets) if targets else None,
                                                   'timeout': timeout, 'deadline': time.time() + timeout}),
                      ttl=int(timeout) + 30)
        raw = self.bus.pop(REPLY_KEY + call_id, timeout + 2)
        return json.loads(raw) if raw else None

    def _serve_call(self, raw):
        try:
            call = json.loads(raw)
        except (TypeError, ValueError):
            return
        try:
            left = float(call.get('deadline') or 0) - time.time()
            call_id, method, timeout = call['id'], call['method'], float(call['timeout'])
        except (TypeError, ValueError, KeyError, AttributeError):
            return                       # not a call this version understands; its caller times out
        if left <= 0:
            return                       # the caller gave up already
        try:
            result = self.run_call(method, call.get('args') or [], call.get('targets'), min(left, timeout))
            reply = {'ok': True, 'result': result}
        except Exception as exc:  # noqa: BLE001  # goes back to the caller as the error
            reply = {'ok': False, 'error': str(exc)[:300], 'unavailable': type(exc).__name__ == 'AgentUnavailable'}
        with contextlib.suppress(Exception):
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
                             (lambda: self.bus.listen(CHANNEL, self._heard, self._stop), 'cluster-events'),
                             (self._take_calls, 'cluster-calls')):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        self.log(f'[cluster] pod {self.pod} joined (Redis)')

    def stop(self):
        self._stop.set()


current = None


def leading():
    """Should this pod act on automatic side effects? Always yes with one pod."""
    return current is None or current.leading()


def init(log=print):
    """Join the cluster when FLOORBIT_CLUSTER=redis. Returns the Cluster or None."""
    global current
    mode = (os.environ.get('FLOORBIT_CLUSTER') or '').strip().lower()
    if mode in ('', 'off', 'none'):
        return None
    if mode != 'redis':
        raise ValueError(f'FLOORBIT_CLUSTER must be "redis" or empty, not "{mode}".')
    from integrations import events

    from . import agent_link, cache
    bus = RedisBus(host=cache.REDIS_HOST, port=cache.REDIS_PORT, db=cache.REDIS_DB, password=cache.REDIS_PASSWORD)
    current = Cluster(bus, deliver=events.deliver_local, run_call=agent_link.tunnel.call_here, log=log)
    current.renew()
    current.start()
    return current
