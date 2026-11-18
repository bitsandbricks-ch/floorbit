"""The hosted side of the local agent (issue #2). See docs/agent.md.

A hosted Floorbit can't reach the event network: LibreNMS and NetBox sit behind the event's
firewall. A small agent runs there instead and opens the connection itself. It asks this instance
for work (a long poll), runs each call against the event's own sources and posts the answers back.
Nothing on the event network has to be reachable from outside.

- **Credentials:** an admin enrols an agent and gets its key once (``fba_<id>_<secret>``); only a
  hash is kept, in data.json under ``agents``. Revoking it stops the agent at its next request.
- **Calls:** ``Tunnel.call()`` queues a monitoring call and waits for the answer. While no agent
  has asked for work recently, a call fails at once, and the monitoring source answers from its
  last good data, marked stale (floorbit/sources/lastgood.py).
- **The source:** with an agent enrolled, ``AgentMonitoring`` is what ``sources.monitoring()``
  returns, so the floor plan, status monitor and check-in page work as with a local LibreNMS.
- **The inventory:** an inventory sync also asks the agent for its inventory plugins' devices
  (``inventory_feeds``), merged under each plugin's own id (floorbit/blueprints/inventory.py),
  and a cable import for their cables (``cable_feeds``, floorbit/cables.py).

One app process (gunicorn runs one worker), so the queue lives in memory.
"""
import collections
import hashlib
import hmac
import itertools
import os
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeout

from .store import load_data, load_shared, save_data

KEY = 'agents'
PREFIX = 'fba_'
MAX_AGENTS = 10
NAME_RE = re.compile(r'^[^\x00-\x1f<>]{1,60}$')
KEY_RE = re.compile(r'^fba_([0-9a-f]{8})_([A-Za-z0-9_-]{20,80})$')
CONNECTED_FOR = 60       # an agent that asked for work this recently counts as connected
ROTATE_GRACE = 24 * 3600  # after a new key, the old one still works this long, or until the new one is used
CALL_TIMEOUT = 8         # seconds a page waits for the agent's answer
MAX_WAIT = 25            # longest long poll, under the usual 30 s proxy timeouts
MAX_PENDING = 200        # calls queued for the agent; more fail at once
# A live agent is always asking for work (a long poll, or its link's loop), so it takes a call within
# moments. One nobody took for TAKE_GRACE, while no agent for it asked in ASKED_RECENTLY, has nobody
# to go to: the agent died without a word (a long-poll agent has no link whose close says so).
TAKE_GRACE = 5
ASKED_RECENTLY = 10
TOUCH_EVERY = 30         # seconds between "last seen" writes to data.json
INVENTORY_TIMEOUT = 25   # a NetBox sync pages through every device: give it longer, under proxy timeouts
# What the agent may be asked: the monitoring source's methods (floorbit/sources), the feeds of
# its plugins (NetBox and others), the game servers' query and RCON (floorbit/game_query.py) and the
# services' DNS and TCP probes (floorbit/probes.py), and switch SSH: port actions, commands and the
# terminal (floorbit/switch_link.py).
METHODS = ('configured', 'devices', 'device_details', 'resolve_ip', 'port_stats', 'device_ports', 'arp',
           'port_clients', 'inventory_feeds', 'cable_feeds', 'health_feeds', 'dns_feeds',
           'wifi_feeds', 'game_query', 'game_rcon', 'neighbours',
           'dns_probe', 'tcp_probe', 'plugin', 'plugins_reload',
           'switch_call', 'shell_open', 'shell_io', 'shell_close', 'plugin_test')
PLUGIN_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_.-]{0,59}$')

_lock = threading.Lock()
_active = None            # ((data file, mtime), is an agent enrolled?)


class AgentError(ValueError):
    status = 400


class AgentUnavailable(RuntimeError):
    """No agent is connected, or it didn't answer in time."""


def _hash(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def _public(a, now):
    seen = a.get('last_seen')
    return {'id': a['id'], 'name': a['name'], 'created_at': a['created_at'], 'created_by': a.get('created_by'),
            'last_seen': seen, 'version': a.get('version'), 'address': a.get('address'), 'protocol': a.get('protocol'),
            'connected': bool(seen and now - seen < CONNECTED_FOR), 'halls': list(a.get('halls') or []),
            'plugins_off': list(a.get('plugins_off') or []), 'local': bool(a.get('local')),
            'renewed_at': a.get('renewed_at') or a['created_at'],
            'old_works_until': a['prev_until'] if a.get('prev_hash') and (a.get('prev_until') or 0) > now else None}


def outdated(agent_protocol, server_protocol=None):
    """Does the agent speak an older protocol than this Floorbit? The agent is released apart
    (bitsandbricks-ch/floorbit-agent), so its version number says nothing next to Floorbit's; the
    protocol does. Unknown: not flagged, no false alarms."""
    server_protocol = PROTOCOL if server_protocol is None else server_protocol
    return isinstance(agent_protocol, int) and agent_protocol < server_protocol


def all_agents(data=None, now=None):
    data = load_data() if data is None else data
    now = time.time() if now is None else now
    out = []
    for a in data.get(KEY) or []:
        row = _public(a, now)
        # last_seen is written only every TOUCH_EVERY: an agent whose link just closed (killed,
        # line cut) is gone now, as the tunnel knows, not up to a minute later.
        row['connected'] = row['connected'] and tunnel.connected(now, a['id'])
        out.append({**row, 'stats': tunnel.stats(a['id'], now), 'relays': tunnel.relays(a['id'], now),
                    'report': tunnel.reported(a['id'], now)})
    return out


def agent_only():
    """Does Floorbit reach the event network only through local agents? Yes, also self-hosted
    (Mike, 2026-11-17: one way for hosted and self-hosted alike, tested the same). ``LAN_ACCESS=direct``
    lets this server call the plugins itself again: for development and tests, not for an event."""
    return (os.environ.get('LAN_ACCESS') or 'agent').strip().lower() != 'direct'


def lan_here():
    """May this process talk to the event network itself? The agent (it has an agent key) may; the
    Floorbit server only with ``LAN_ACCESS=direct``."""
    return not agent_only() or bool(os.environ.get('FLOORBIT_AGENT_KEY'))


def may_call_here(spec):
    """May this server ask a plugin's LAN methods itself? The demo plugin has no LAN, and a plugin
    with an agent part answers from what its agent sent."""
    return lan_here() or spec is None or spec.id == 'demo' or 'agent' in (spec.uses or ())


def active():
    """Does this server ask the event network's questions through the agent? Always, unless
    ``LAN_ACCESS=direct`` or the demo data stands in for the hall; with direct access, once an agent
    is enrolled. Every monitoring call asks, so the enrolment is kept until data.json changes."""
    if agent_only() and not lan_here() and not _demo_on():
        return True
    return _enrolled()


def _demo_on():
    from . import sources
    return bool(sources.registry is not None and sources.registry.demo_on())


def _enrolled():
    global _active
    from . import store
    # Agents are the tenant's, the halls they serve the event's: either changing counts.
    path = store.event_file()
    stamp = (path, store.stamp(path), store.stamp(store.tenant_file()))
    if stamp[1] is None and stamp[2] is None:
        return False
    if _active is None or _active[0] != stamp:
        _active = (stamp, bool(load_data().get(KEY)))
    return _active[1]


def _forget_cache():
    global _active, _routes
    _active = _routes = None
    _doors.clear()


_routes = None   # ((data file, mtime), routing)


def _routing():
    """(agents that serve only some halls -> those halls, every agent id, switch name -> hall),
    kept until data.json changes: it's asked on every monitoring call."""
    global _routes
    from . import halls, inventory, store
    # Agents are the tenant's, the halls they serve the event's: either changing counts.
    path = store.event_file()
    stamp = (path, store.stamp(path), store.stamp(store.tenant_file()))
    if stamp[1] is None and stamp[2] is None:
        return {}, [], {}
    if _routes is None or _routes[0] != stamp:
        data = load_data()
        agents = data.get(KEY) or []
        scoped = {a['id']: frozenset(a['halls']) for a in agents if a.get('halls')}
        by_name = {}
        if scoped:
            ids = {h['id'] for h in halls.halls(data)}
            for dev in inventory.devices(data, include_hidden=True):
                by_name.setdefault(str(dev['name']).lower(), halls.hall_of(dev, data, ids))
        _routes = (stamp, (scoped, [a['id'] for a in agents], by_name))
    return _routes[1]


def enrolled(agent_id):
    """Is this agent still enrolled? An open WebSocket link asks every few seconds, so revoking a
    key also ends the link it already has (docs/agent.md)."""
    return agent_id in _routing()[1]


# What an agent may report about itself (the agent's report(), floorbit-agent issue #3).
REPORT_KEYS = ('up_seconds', 'reconnects', 'link_drops', 'calls_busy', 'answers_failed',
               'syslog_received', 'syslog_sent', 'syslog_dropped', 'syslog_backlog', 'flows_packets',
               'captive_shown', 'captive_done', 'front_door_passed', 'front_door_failed')
REPORT_FRESH = 180        # seconds: an older report says more about the past than about now


# The first argument is a switch.
HOST_METHODS = ('device_details', 'port_stats', 'device_ports', 'port_clients', 'neighbours')


def _hall_of(by_name, hostname):
    name = str(hostname or '').lower()
    return by_name.get(name) or by_name.get(name.split('.')[0])


def _agent_back():
    from . import sources
    sources.wake_status_monitor()


def ask(method, args=()):
    """A monitoring call, sent to the right agent.

    While no agent is limited to some halls, any agent answers (one queue). Once one is: a call
    about a switch goes to an agent for that switch's hall, and a call about everything (the device
    list, an IP, ARP) goes to every connected agent, and their answers are put together."""
    scoped, everyone, by_name = _routing()
    if not scoped:
        # Two agents for the same halls (VIPs shared with VRRP, the agent's docs/vrrp.md): only the
        # primary one collects telemetry, so ask both and keep the answer that has something.
        if len(tunnel.connected_agents() & set(everyone)) < 2:
            return tunnel.call(method, args)
        return _ask_all(method, args, everyone)
    if method in HOST_METHODS and args:
        hall = _hall_of(by_name, args[0])
        if hall is None:        # a switch Floorbit doesn't know: whoever answers
            return tunnel.call(method, args)
        return tunnel.call(method, args, targets={a for a in everyone if a not in scoped or hall in scoped[a]})
    return _ask_all(method, args, everyone)


def agent_for(hostname):
    """The one connected agent that should talk to this switch: one serving its hall, else any.
    For calls that hold something open on the agent (an SSH shell) or must not run twice (a port
    bounce), where ``ask()`` would ask every agent. Raises AgentUnavailable."""
    scoped, everyone, by_name = _routing()
    connected = tunnel.connected_agents() & set(everyone)
    if scoped:
        hall = _hall_of(by_name, hostname)
        if hall is not None:
            connected = {a for a in connected if a not in scoped or hall in scoped[a]}
    if not connected:
        raise AgentUnavailable(f'No local agent that reaches {hostname} is connected.')
    return sorted(connected)[0]


HEDGE_AFTER = 3.0      # seconds: a lookup burst answers in under 2; longer means that agent hangs
_last_knew = [None]    # the agent that answered the last first-answer call
FIRST_ANSWER = {'resolve_ip'}   # None when an agent doesn't know: the first real answer is the answer


def _ask_all(method, args, everyone):
    """Every connected agent, the answers put together."""
    agents = sorted(tunnel.connected_agents() & set(everyone))
    if not agents:
        raise AgentUnavailable('No local agent is connected.')
    results, errors = [], []
    pool = ThreadPoolExecutor(len(agents))
    asked = {}     # future -> agent

    def ask_one(agent):
        fut = pool.submit(tunnel.call, method, args, CALL_TIMEOUT, {agent})
        asked[fut] = agent
        return fut

    try:
        rest = agents
        if method in FIRST_ANSWER and len(agents) > 1:
            # Two agents for one hall would each ask LibreNMS about every seat. Ask the one that
            # knew last; the others only when it doesn't know, fails or hangs past HEDGE_AFTER.
            first = _last_knew[0] if _last_knew[0] in agents else agents[0]
            rest = [a for a in agents if a != first]
            lead = ask_one(first)
            try:
                found = lead.result(timeout=HEDGE_AFTER)
            except FutureTimeout:
                pass                       # still running: it joins the others below
            except (AgentUnavailable, AgentError) as exc:
                errors.append(exc)
                del asked[lead]
            else:
                if found:
                    return found
                results.append(found)
                del asked[lead]
        for agent in rest:
            ask_one(agent)
        for fut in as_completed(list(asked)):
            try:
                results.append(fut.result())
            except (AgentUnavailable, AgentError) as exc:
                errors.append(exc)
                continue
            if method in FIRST_ANSWER and results[-1]:
                # The agent that knows it: don't wait for one that was just killed (a check-in
                # held up to CALL_TIMEOUT during a failover).
                _last_knew[0] = asked[fut]
                return results[-1]
    finally:
        pool.shutdown(wait=False)
    if not results:
        raise errors[0]
    if method == 'devices':
        merged, seen = [], set()
        for result in results:
            for d in result or []:
                key = str(d.get('hostname') or d.get('display') or id(d)).lower() if isinstance(d, dict) else id(d)
                if key not in seen:
                    seen.add(key)
                    merged.append(d)
        return merged
    if method == 'arp':
        merged, seen = [], set()
        for row in (row for result in results for row in result or []):
            key = (row.get('ipv4_address'), row.get('mac_address'), row.get('hostname')) \
                if isinstance(row, dict) else id(row)
            if key not in seen:
                seen.add(key)
                merged.append(row)
        return merged
    if method == 'configured':
        return any(results)
    return next((r for r in results if r), None)     # resolve_ip: the agent that knows it


def enrol(name, by, now=None):
    """A new agent. Returns (its record, the key): the key is shown this once."""
    name = str(name or '').strip()
    if not NAME_RE.match(name):
        raise AgentError('Give the agent a name of up to 60 characters, such as the event or the site.')
    now = time.time() if now is None else now
    with _lock:
        data = load_data()
        agents = data.setdefault(KEY, [])
        if len(agents) >= MAX_AGENTS:
            raise AgentError(f'At most {MAX_AGENTS} agents. Revoke one you no longer use.')
        agent_id = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        record = {'id': agent_id, 'name': name, 'hash': _hash(secret), 'created_at': now, 'created_by': by,
                  'last_seen': None, 'version': None, 'address': None}
        agents.append(record)
        save_data(data)
    _forget_cache()
    return _public(record, now), f'{PREFIX}{agent_id}_{secret}'


LOCAL_ID = '10ca1000'       # the agent next to a self-hosted Floorbit: one fixed id, so restarts don't pile up agents
LOCAL_KEY_FILE_ENV = 'FLOORBIT_LOCAL_AGENT_KEY_FILE'


def _local_key_file():
    return (os.environ.get(LOCAL_KEY_FILE_ENV) or '').strip()


def _write_key_file(path, key):
    """The key, readable only by the image's user (the agent container runs as the same one)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), mode=0o700, exist_ok=True)
    tmp = path + '.tmp'
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as f:
        f.write(key + '\n')
    os.replace(tmp, path)


def bootstrap_local(path=None, now=None):
    """Self-hosted, Floorbit and its agent start side by side (docker-compose.yml, the Kubernetes
    pod) and share ``FLOORBIT_LOCAL_AGENT_KEY_FILE``: this side writes the key there and enrols the
    agent ("Local agent"), so nobody has to copy a key from Settings. The file is the truth: a key
    written by hand is taken over. Returns the agent id, or None when not set up this way."""
    path = path or _local_key_file()
    if not path or not agent_only() or os.environ.get('FLOORBIT_AGENT_KEY'):
        return None
    now = time.time() if now is None else now
    try:
        with open(path, encoding='utf-8') as f:
            m = KEY_RE.match(f.read().strip())
    except OSError:
        m = None
    if m:
        agent_id, secret = m.groups()
    else:
        agent_id, secret = LOCAL_ID, secrets.token_urlsafe(32)
        _write_key_file(path, f'{PREFIX}{agent_id}_{secret}')
    digest = _hash(secret)
    with _lock:
        data = load_data()
        agents = data.setdefault(KEY, [])
        found = next((a for a in agents if a['id'] == agent_id), None)
        if found is None:
            agents.append({'id': agent_id, 'name': 'Local agent', 'hash': digest, 'created_at': now,
                           'created_by': 'setup', 'last_seen': None, 'version': None, 'address': None,
                           'local': True})
        elif found['hash'] != digest or found.get('prev_hash'):
            found.update(hash=digest, local=True, renewed_at=now)
            found.pop('prev_hash', None)
            found.pop('prev_until', None)
        else:
            return agent_id
        save_data(data)
    _forget_cache()
    return agent_id


def revoke(agent_id):
    with _lock:
        data = load_data()
        agents = data.get(KEY) or []
        found = next((a for a in agents if a['id'] == agent_id), None)
        if not found:
            err = AgentError('No such agent.')
            err.status = 404
            raise err
        data[KEY] = [a for a in agents if a['id'] != agent_id]
        save_data(data)
    _forget_cache()
    return found['name']


def _change(agent_id, fn):
    """Apply ``fn(record)`` to one agent under the lock; returns the record. 404 for no such agent."""
    with _lock:
        data = load_data()
        found = next((a for a in data.get(KEY) or [] if a['id'] == agent_id), None)
        if not found:
            err = AgentError('No such agent.')
            err.status = 404
            raise err
        fn(found)
        save_data(data)
    _forget_cache()
    return found


def rotate(agent_id, now=None):
    """A new key for an agent. The old one keeps working until the agent first uses the new one,
    at most ROTATE_GRACE, so the hall can swap it without the agent going dark. Returns (name, key)."""
    now = time.time() if now is None else now
    secret = secrets.token_urlsafe(32)

    def swap(a):
        a.update(prev_hash=a['hash'], prev_until=now + ROTATE_GRACE, hash=_hash(secret), renewed_at=now)
    found = _change(agent_id, swap)
    key = f'{PREFIX}{agent_id}_{secret}'
    if found.get('local') and _local_key_file():
        # The agent next to us reads it from the shared file: it takes it at its next start, and
        # the old key keeps working until then (ROTATE_GRACE).
        try:
            _write_key_file(_local_key_file(), key)
        except OSError as exc:
            print(f'[agent] cannot write the new key to {_local_key_file()}: {exc}', flush=True)
    return found['name'], key


def rename(agent_id, name):
    name = str(name or '').strip()
    if not NAME_RE.match(name):
        raise AgentError('Give the agent a name of up to 60 characters, such as the event or the site.')
    old = {}

    def set_name(a):
        old['name'] = a['name']
        a['name'] = name
    _change(agent_id, set_name)
    return old['name'], name


def set_plugins_off(agent_id, plugin_ids):
    """The plugins this agent doesn't run though they are on here (another agent runs them)."""
    if not isinstance(plugin_ids, list) or not all(isinstance(p, str) for p in plugin_ids):
        raise AgentError('plugins_off must be a list of plugin ids.')
    wanted = sorted({p for p in plugin_ids if re.match(r'^[a-z][a-z0-9-]{0,39}$', p)})
    found = _change(agent_id, lambda a: a.__setitem__('plugins_off', wanted))
    return found['name'], wanted


def plugins_off(agent_id):
    found = next((a for a in load_data().get(KEY) or [] if a['id'] == agent_id), None)
    return set((found or {}).get('plugins_off') or [])


def set_halls(agent_id, hall_ids):
    """The halls an agent answers for; empty means every hall. Returns the cleaned list."""
    from . import halls
    if not isinstance(hall_ids, list):
        raise AgentError('halls must be a list of hall ids.')
    with _lock:
        data = load_data()
        known = {h['id'] for h in halls.halls(data)}
        wanted = []
        for h in hall_ids:
            if str(h) not in known:
                raise AgentError(f'No hall "{h}".')
            if str(h) not in wanted:
                wanted.append(str(h))
        found = next((a for a in data.get(KEY) or [] if a['id'] == agent_id), None)
        if not found:
            err = AgentError('No such agent.')
            err.status = 404
            raise err
        found['halls'] = wanted
        save_data(data)
    _forget_cache()
    return found['name'], wanted


def check(key, version=None, address=None, now=None, protocol=None):
    """The agent a key belongs to, or None. Notes when it was last seen (now and then)."""
    m = KEY_RE.match(str(key or '').strip())
    if not m:
        return None
    now = time.time() if now is None else now
    agent_id, secret = m.groups()
    data = load_shared()     # every agent request asks: don't parse data.json each time
    found = next((a for a in data.get(KEY) or [] if a['id'] == agent_id), None)
    if not found:
        return None
    if hmac.compare_digest(found['hash'], _hash(secret)):
        if found.get('prev_hash'):
            # The new key is in use: the old one stops working now.
            with _lock:
                data = load_data()
                for a in data.get(KEY) or []:
                    if a['id'] == agent_id:
                        a.pop('prev_hash', None)
                        a.pop('prev_until', None)
                save_data(data)
    elif not (found.get('prev_hash') and (found.get('prev_until') or 0) > now
              and hmac.compare_digest(found['prev_hash'], _hash(secret))):
        return None
    tunnel.seen(now, agent_id)
    try:
        protocol = int(protocol) if protocol is not None else None
    except (TypeError, ValueError):
        protocol = None
    if (not found.get('last_seen') or now - found['last_seen'] >= TOUCH_EVERY or found.get('version') != version
            or found.get('protocol') != protocol):
        with _lock:
            data = load_data()
            for a in data.get(KEY) or []:
                if a['id'] == agent_id:
                    a.update(last_seen=now, version=(str(version)[:40] if version else None),
                             address=(str(address)[:64] if address else None), protocol=protocol)
            save_data(data)
    return {'id': found['id'], 'name': found['name']}


_doors = {}               # key -> (agent id or None, checked at): front-door requests come per asset
DOOR_RECHECK = 30         # seconds a key's answer is kept; a revoked key stops working within this


def front_door(key, now=None):
    """The id of the agent whose front door passed this request on, or None (agent's front_door.py).
    Only checks the key: the request is an attendee's, not the agent's own."""
    key = str(key or '').strip()
    m = KEY_RE.match(key)
    if not m:
        return None
    now = time.monotonic() if now is None else now
    cached = _doors.get(key)
    if cached and now - cached[1] < DOOR_RECHECK:
        return cached[0]
    agent_id, secret = m.groups()
    found = next((a for a in load_data().get(KEY) or [] if a['id'] == agent_id), None)
    wall = time.time()
    ok = bool(found) and (hmac.compare_digest(found['hash'], _hash(secret)) or bool(
        found.get('prev_hash') and (found.get('prev_until') or 0) > wall
        and hmac.compare_digest(found['prev_hash'], _hash(secret))))
    if len(_doors) > 50:            # only ever a few real keys: don't let guesses grow it
        _doors.clear()
    _doors[key] = (agent_id if ok else None, now)
    return _doors[key][0]


# ── The call tunnel ────────────────────────────────────────────────────────────────────────────

# The agent protocol (/api/agent/v1, docs/agent.md "The protocol"). The agent lives in its own
# repository, so the two are released apart: a change the other side can't follow gets a new number.
# 2 adds the WebSocket link (/api/agent/v2/link); everything from 1 stays as it was.
PROTOCOL = 2
PROTOCOLS = (1, 2)        # what this Floorbit understands
RELAY_RECENT = 600       # syslog or flows sent within this long count as relayed
STATS_WINDOW = 3600      # the Local agents page shows the last hour's calls
STATS_KEEP = 5000        # answers kept per agent for that, at most


class _Call:
    __slots__ = ('agent', 'args', 'done', 'error', 'id', 'method', 'ok', 'result', 'taken', 'taken_at', 'targets',
                 'unavailable')

    def __init__(self, call_id, method, args, targets=None):
        self.id, self.method, self.args = call_id, method, args
        self.targets = targets     # agent ids that may take it; None: any
        self.done = threading.Event()
        self.ok, self.result, self.error, self.taken = False, None, None, False
        self.agent, self.taken_at = None, None
        self.unavailable = False


class Tunnel:
    def __init__(self):
        self._cond = threading.Condition()
        self._pending = collections.deque()
        self._calls = {}
        self._ids = itertools.count(1)
        self._stats = {}          # agent id -> deque of (when, ms, ok, method, error)
        self._seen = {}           # agent id -> when it last asked for work
        self._relayed = {}        # agent id -> {"syslog" | "flows": {"at", "count"}}
        self._reports = {}        # agent id -> the agent's own numbers, as it last sent them
        self._links = {}          # agent id -> WebSocket links open to this pod
        self._asking = {}         # agent id -> None while in take(), else when it last left it
        self.last_seen = None

    def reset(self):
        with self._cond:
            self._pending.clear()
            self._calls.clear()
            self._stats.clear()
            self._seen.clear()
            self._links.clear()
            self._asking.clear()
            self._relayed.clear()
            self._reports.clear()
            self.last_seen = None

    def relayed(self, agent, kind, count=0, now=None):
        """An agent sent syslog or a flow summary: the Local agents page shows what each one relays."""
        now = time.time() if now is None else now
        with self._cond:
            seen = self._relayed.setdefault(agent, {}).setdefault(kind, {'at': now, 'count': 0})
            seen['at'] = now
            seen['count'] += count

    def relays(self, agent, now=None):
        """{kind: {"at", "count"}} for what the agent sent in the last RELAY_RECENT seconds."""
        now = time.time() if now is None else now
        with self._cond:
            return {kind: dict(v) for kind, v in self._relayed.get(agent, {}).items() if now - v['at'] < RELAY_RECENT}

    def _back(self, agent, now):
        """Was the agent away until now? Then the monitoring source answers again: the status
        monitor checks right away instead of within its interval, during which every lookup was
        answered from old data (a restart of the agent or of Floorbit cost up to a minute)."""
        last = self._seen.get(agent)
        return last is None or now - last > CONNECTED_FOR

    def seen(self, now=None, agent=None):
        self.last_seen = time.time() if now is None else now
        if agent is not None:
            back = self._back(agent, self.last_seen)
            self._seen[agent] = self.last_seen
            if back:
                _agent_back()
            from . import cluster
            if cluster.current is not None:
                cluster.current.agent_seen(agent, self.last_seen)

    def waiting_on(self, agent, older_than, now=None):
        """Has the agent held a call for longer than ``older_than`` seconds without answering?"""
        now = time.monotonic() if now is None else now
        with self._cond:
            return any(c.agent == agent and c.taken_at is not None and not c.done.is_set()
                       and now - c.taken_at > older_than for c in self._calls.values())

    def seen_on_link(self, agent, now=None):
        """seen() from a WebSocket link, only while it is open: the link's loop may still be in its
        last turn when the reader found it closed, and must not bring the agent back."""
        now = time.time() if now is None else now
        with self._cond:
            if not self._links.get(agent):
                return False
            back = self._back(agent, now)
            self.last_seen = self._seen[agent] = now
        if back:
            _agent_back()
        from . import cluster
        if cluster.current is not None:
            cluster.current.agent_seen(agent, now)
        return True

    def linked(self, agent):
        with self._cond:
            self._links[agent] = self._links.get(agent, 0) + 1

    def unlinked(self, agent, now=None):
        """An agent's WebSocket link closed. When it was its last one, the agent is gone now, not
        CONNECTED_FOR later: a killed agent or a dropped line would otherwise hold every page for
        CALL_TIMEOUT. Calls only it could take fail at once (pages answer from their last good
        data), and so do the ones it had taken: their answers can't come back on a closed link."""
        now = time.time() if now is None else now
        with self._cond:
            left = self._links.get(agent, 0) - 1
            if left > 0:
                self._links[agent] = left
                return False
            self._links.pop(agent, None)
            self._seen.pop(agent, None)
            self.last_seen = max(self._seen.values(), default=None)
            alive = {a for a, seen in self._seen.items() if now - seen < CONNECTED_FOR}
            for call in list(self._calls.values()):
                if call.done.is_set():
                    continue
                if call.taken:
                    lost = call.agent == agent
                    reason = (f'The local agent went away before it answered {call.method}; '
                              'it may have run. Look before trying again.')
                else:
                    lost = not (alive if call.targets is None else call.targets & alive)
                    reason = 'The local agent is not connected.'
                if lost:
                    if call in self._pending:
                        self._pending.remove(call)
                    call.ok, call.error, call.unavailable = False, reason, True
                    call.done.set()
        from . import cluster
        if cluster.current is not None:
            cluster.current.agent_left(agent)
        return True

    def _here(self, now, agent=None):
        seen = self.last_seen if agent is None else self._seen.get(agent)
        return seen is not None and now - seen < CONNECTED_FOR

    def _elsewhere(self, now):
        """{agent id: pod} for agents connected to another pod (several pods, floorbit/cluster.py)."""
        from . import cluster
        return cluster.current.agents_elsewhere(now) if cluster.current is not None else {}

    def connected(self, now=None, agent=None):
        """Is any agent (or this one) connected, to this pod or another?"""
        now = time.time() if now is None else now
        if self._here(now, agent):
            return True
        elsewhere = self._elsewhere(now)
        return bool(elsewhere) if agent is None else agent in elsewhere

    def connected_agents(self, now=None):
        now = time.time() if now is None else now
        return {a for a, seen in list(self._seen.items()) if now - seen < CONNECTED_FOR} | set(self._elsewhere(now))

    def call(self, method, args=(), timeout=CALL_TIMEOUT, targets=None):
        """Ask an agent (one of ``targets``, any when None); returns its answer. Raises
        AgentUnavailable, or AgentError with its error. With several pods, an agent connected to
        another pod is asked through that pod."""
        if method not in METHODS:
            raise AgentError(f'{method} is not something the agent answers.')
        now = time.time()
        here = {a for a, seen in list(self._seen.items()) if now - seen < CONNECTED_FOR}
        local = bool(here & set(targets)) if targets is not None else self._here(now)
        if not local:
            pods = {pod for agent, pod in self._elsewhere(now).items() if targets is None or agent in targets}
            if pods:
                from . import cluster
                answer = cluster.current.forward(sorted(pods)[0], method, list(args),
                                                 set(targets) if targets is not None else None, timeout)
                if answer is None:
                    raise AgentUnavailable(f'The local agent did not answer {method} within {timeout} s.')
                if answer.get('ok'):
                    return answer.get('result')
                raise (AgentUnavailable if answer.get('unavailable') else AgentError)(
                    answer.get('error') or f'{method} failed on the agent.')
        return self.call_here(method, args, timeout, targets)

    def call_here(self, method, args=(), timeout=CALL_TIMEOUT, targets=None):
        """Ask an agent connected to this pod."""
        if method not in METHODS:
            raise AgentError(f'{method} is not something the agent answers.')
        if targets is not None:
            now = time.time()
            targets = frozenset(targets)
            if not targets & {a for a, seen in list(self._seen.items()) if now - seen < CONNECTED_FOR}:
                raise AgentUnavailable('No local agent for this hall is connected.')
        elif not self._here(time.time()):
            raise AgentUnavailable('The local agent is not connected.')
        with self._cond:
            if len(self._pending) >= MAX_PENDING:
                raise AgentUnavailable('The local agent has too much to do.')
            call = _Call(str(next(self._ids)), method, list(args), targets)
            self._calls[call.id] = call
            self._pending.append(call)
            self._cond.notify_all()
        try:
            grace = min(timeout, TAKE_GRACE)
            if not call.done.wait(grace):
                with self._cond:
                    gone = [] if call.taken else self._nobody_asking(targets, time.monotonic())
                    for agent in gone:
                        self._seen.pop(agent, None)      # the next calls fail at once, not after the grace
                    if gone:
                        self.last_seen = max(self._seen.values(), default=None)
                if gone:
                    raise AgentUnavailable('The local agent is not connected.')
                if not call.done.wait(timeout - grace):
                    raise AgentUnavailable(f'The local agent did not answer {method} within {timeout} s.')
        finally:
            with self._cond:
                self._calls.pop(call.id, None)
                if call in self._pending:
                    self._pending.remove(call)
        if not call.ok:
            raise (AgentUnavailable if call.unavailable else AgentError)(call.error or f'{method} failed on the agent.')
        return call.result

    def take(self, wait=MAX_WAIT, limit=20, agent=None):
        """The calls waiting for the agent, waiting up to ``wait`` seconds for the first one."""
        deadline = time.monotonic() + max(0.0, min(float(wait), MAX_WAIT))

        def mine(call):
            return call.targets is None or agent in call.targets

        with self._cond:
            self._asking[agent] = None
            try:
                while not any(mine(c) for c in self._pending):
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return []
                    self._cond.wait(left)
                out = []
                for call in list(self._pending):
                    if len(out) >= limit:
                        break
                    if mine(call):
                        self._pending.remove(call)
                        call.taken, call.agent, call.taken_at = True, agent, time.monotonic()
                        out.append({'id': call.id, 'method': call.method, 'args': call.args})
                return out
            finally:
                self._asking[agent] = time.monotonic()

    def _nobody_asking(self, targets, now):
        """The agents (of ``targets``) that should have taken a call but didn't ask lately; empty
        when one of them is asking. Called under the lock."""
        mine = [a for a in self._seen if targets is None or a in targets]
        quiet = [a for a in mine if self._asking.get(a, 0) is not None
                 and now - (self._asking.get(a) or 0) > ASKED_RECENTLY]
        return quiet if len(quiet) == len(mine) else []

    def give_back(self, taken):
        """Calls an agent took but can't deliver (its link closed meanwhile): another agent, or
        this one once it is back, takes them instead of the caller waiting out its timeout."""
        with self._cond:
            for item in reversed(taken):
                call = self._calls.get(str(item['id']))
                if call is not None and call.taken and not call.done.is_set():
                    call.taken, call.agent, call.taken_at = False, None, None
                    self._pending.appendleft(call)
            self._cond.notify_all()

    def answer(self, call_id, ok, result=None, error=None, agent=None):
        """The agent's answer to one call. False when nobody waits for it any more, or when another
        agent took it: one site's agent must not answer for another's."""
        with self._cond:
            call = self._calls.get(str(call_id))
        if call is None or (agent is not None and call.agent is not None and call.agent != agent):
            return False
        call.ok, call.result, call.error = bool(ok), result, (str(error)[:300] if error else None)
        call.done.set()
        if call.agent is not None and call.taken_at is not None:
            ms = (time.monotonic() - call.taken_at) * 1000
            with self._cond:
                log = self._stats.setdefault(call.agent, collections.deque(maxlen=STATS_KEEP))
                log.append((time.time(), ms, call.ok, call.method, call.error))
        return True

    def report(self, agent, raw, now=None):
        """The agent's own numbers (floorbit-agent's /metrics, summed up), sent every half minute.
        Only known keys, only numbers: what an agent sends is not trusted."""
        if not isinstance(raw, dict):
            return
        clean = {k: raw[k] for k in REPORT_KEYS
                 if isinstance(raw.get(k), (int, float)) and not isinstance(raw.get(k), bool) and raw[k] >= 0}
        from .agent_plugins import clean_health
        plugins = clean_health(raw.get('plugins'))
        if plugins:
            clean['plugins'] = plugins
        from .agent_plugins import clean_updates, clean_vrrp
        for key, cleaner in (('updates', clean_updates), ('vrrp', clean_vrrp)):
            value = cleaner(raw.get(key))
            if value is not None:
                clean[key] = value
        # Where laptops on the event network reach the agent (the seat walk-through, seat_walk.py).
        lan_url = raw.get('lan_url')
        if isinstance(lan_url, str) and re.match(r'^https?://[A-Za-z0-9.:\[\]-]{1,120}(/[^\s]{0,60})?$', lan_url):
            clean['lan_url'] = lan_url
        clean['at'] = time.time() if now is None else now
        with self._cond:
            before = self._reports.get(agent)
            self._reports[agent] = clean
        if plugins:
            from .agent_plugins import note_blocks
            note_blocks(agent, before, clean)
        if clean.get('updates'):
            from .agent_plugins import note_updates
            note_updates(agent, before, clean, now=clean['at'])

    def reported(self, agent, now=None):
        """What the agent last reported, or None when it never did or it's older than REPORT_FRESH."""
        now = time.time() if now is None else now
        with self._cond:
            found = self._reports.get(agent)
        return dict(found) if found and now - found['at'] < REPORT_FRESH else None

    def stats(self, agent, now=None):
        """The last hour of one agent's answers: how many, how many failed, the median time, the
        last error. Kept in memory only, so a restart starts over."""
        now = time.time() if now is None else now
        with self._cond:
            recent = [r for r in self._stats.get(agent) or () if now - r[0] < STATS_WINDOW]
        if not recent:
            return {'calls': 0, 'failed': 0, 'median_ms': None, 'last_error': None}
        times = sorted(r[1] for r in recent)
        failed = [r for r in recent if not r[2]]
        last = failed[-1] if failed else None
        return {'calls': len(recent), 'failed': len(failed), 'median_ms': round(times[len(times) // 2]),
                'last_error': {'at': last[0], 'method': last[3], 'error': last[4]} if last else None}


tunnel = Tunnel()


def inventory_feeds():
    """The agent's inventory plugins and their devices: ``[{plugin, name, items | error}]``."""
    return feeds('inventory_feeds')


def cable_feeds():
    """The agent's plugins that know cables (NetBox) and their cables, as ``inventory_feeds``."""
    return feeds('cable_feeds')


def feeds(method, args=()):
    """``[{plugin, name, base, base_name, items | error}]`` from the agent. Raises AgentUnavailable
    or AgentError. Feeds that don't look right are dropped.

    Once an agent serves only some halls, every connected agent is asked, and each one's feeds get
    their own id (``netbox.<agent id>``): two sites' NetBox servers must not mark each other's
    devices gone. ``base`` and ``base_name`` stay the plugin's own."""
    scoped, everyone, _ = _routing()
    if not scoped:
        return _clean_feeds(tunnel.call(method, args, timeout=INVENTORY_TIMEOUT))
    agents = sorted(tunnel.connected_agents() & set(everyone))
    if not agents:
        raise AgentUnavailable('No local agent is connected.')
    names = {a['id']: a['name'] for a in load_data().get(KEY) or []}
    out = []
    with ThreadPoolExecutor(len(agents)) as pool:
        futures = [(a, pool.submit(tunnel.call, method, args, INVENTORY_TIMEOUT, {a})) for a in agents]
        for agent, fut in futures:
            try:
                got = _clean_feeds(fut.result())
            except (AgentUnavailable, AgentError) as exc:
                out.append({'plugin': f'agent.{agent}', 'name': names.get(agent, agent), 'base': f'agent.{agent}',
                            'base_name': names.get(agent, agent), 'error': str(exc)[:300]})
                continue
            for f in got:
                f.update(plugin=f"{f['plugin']}.{agent}", name=f"{f['name']}, {names.get(agent, agent)}"[:60])
                out.append(f)
    return out


def _clean_feeds(feeds):
    out = []
    for f in feeds if isinstance(feeds, list) else []:
        if not isinstance(f, dict) or not PLUGIN_ID_RE.match(str(f.get('plugin') or '')):
            continue
        name = str(f.get('name') or f['plugin'])[:60]
        base = {'plugin': f['plugin'], 'name': name, 'base': f['plugin'], 'base_name': name}
        if f.get('error') or not isinstance(f.get('items'), list):
            out.append({**base, 'error': str(f.get('error') or 'no devices sent')[:300]})
        else:
            out.append({**base, 'items': f['items']})
    return out


# ── The monitoring source it feeds ─────────────────────────────────────────────────────────────

def monitoring_source():
    """The agent-fed monitoring source (floorbit/sources), made here to keep the import late."""
    from .plugins.base import PluginError
    from .sources import PluginMonitoring

    class AgentMonitoring(PluginMonitoring):
        """``sources.monitoring()`` while an agent is enrolled: every call goes through the tunnel.
        A failed or unanswered call is a PluginError, so the last good answer is used, marked stale."""

        def __init__(self):   # no registry or plugin spec: the plugin runs on the agent
            self.name = 'agent'
            self.label = 'Local agent'

        def _call(self, method, *args):
            try:
                return ask(method, args)
            except (AgentUnavailable, AgentError) as exc:
                raise PluginError(str(exc)) from None

        def enabled(self):
            return True

        def device_ports(self, hostname):
            from . import sources
            if sources.offline():
                return []
            try:
                return self._call('device_ports', hostname) or []
            except PluginError as exc:
                print(f'[agent] device_ports failed: {exc}')
                return []

        def port_clients(self, hostname):
            return self._call('port_clients', hostname) or []

        def neighbours(self, hostname):
            return self._call('neighbours', hostname) or []

    return AgentMonitoring()
