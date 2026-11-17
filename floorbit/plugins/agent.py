"""Agent plugins: the part of a plugin that runs on the local agent, in the hall.

A plugin that needs something only the event network has (a log file on the LAN cache, a UDP
port the switches send to, a device the hosted Floorbit can't reach) lists ``agent`` under
``uses:`` and adds an ``agent:`` block to ``plugin.yaml``::

    uses: [agent, actions, widgets]
    agent:
      module: agent.py            # class AgentPlugin(floorbit.plugins.agent.AgentPlugin)
      sends:                      # what it posts to the hosted Floorbit, and how private it is
        stats: {privacy: aggregate}
      calls: [status]             # read-only questions the hosted side may ask (call_status)
      actions: [clear_cache]      # changes the hosted side may ask for (action_clear_cache)

The agent runs ``agent.py``; the hosted Floorbit runs ``plugin.py`` as for any plugin. They talk
three ways, all over the agent's link (TLS, the agent key, docs/agent.md):

* **send**: the agent part posts ``ctx.send(kind, payload)``; the hosted part gets it in
  ``Plugin.agent_<kind>(agent, payload)``. Spooled on the agent's disk while the uplink is down.
  A kind marked ``privacy: aggregate`` is refused, on both sides, when it holds an IP or a MAC
  address: hall-wide numbers only (5 or more clients, docs/privacy.md).
* **calls**: the hosted part asks ``self.ctx.agent_call('status', args)``; the agent part answers
  in ``call_status(args)``. Read-only.
* **actions**: ``self.ctx.agent_action('clear_cache', params)`` from one of the plugin's own
  actions (so the role check and the audit log are the ones every plugin action gets), answered by
  ``action_clear_cache(params)`` on the agent. The hall must allow it as well: the agent runs an
  action only when ``FLOORBIT_AGENT_ALLOW_ACTIONS`` names it (``lancache.clear_cache``,
  ``lancache.*`` or ``*``), so a stolen hosted login can't change things in the hall by itself.

Logins: before it logs in to a device, an agent part asks ``ctx.may_login(device, credential,
rev)``; when the device refuses the credential it says ``ctx.auth_failed(device, credential, rev,
message)``. From then on that device and credential are left alone until a tech clears it on the
Local agents page (or the credential is edited: a new ``rev``), so a wrong password never locks
an account out or sets off the AAA server. The block is reported, audit-logged on the hosted side,
and kept on the agent's disk.

Health: an agent part says how it is doing with ``ctx.health(...)``, ``ctx.error(...)``,
``ctx.counter(...)`` and ``ctx.gauge(...)``. They go into the agent's ``/metrics`` and its report
every half minute, and the hosted Local agents page shows them per plugin.

Only plugins that ship with Floorbit (the agent image is built from it) run on an agent: no code
is downloaded. Settings come from the hosted Floorbit (secrets too, decrypted for the agent and
sent over the link only).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import threading
import time
from collections import deque

from .base import PluginError

__all__ = ['PRIVACY', 'AgentPlugin', 'MemoryContext', 'check_agent_block', 'personal_data']

PRIVACY = ('aggregate', 'device')
CREDENTIAL_KINDS = ('ssh', 'snmp_v2c', 'snmp_v3', 'api', 'http')
KIND_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
STATUSES = ('ok', 'warning', 'error', 'off')
SEND_MAX_BYTES = 4 * 1024 * 1024      # one payload, as JSON
ERRORS_KEPT = 10
METRICS_KEPT = 40                     # numbers per plugin in the report: /metrics has them all


def check_agent_block(m):
    """An error message for the manifest's ``agent:`` block, or ''. Normalises it in place."""
    block = m.get('agent')
    uses = m.get('uses') or []
    if block is None:
        return 'agent: the plugin uses "agent" but has no agent: block' if 'agent' in uses else ''
    if 'agent' not in uses:
        return 'agent: the plugin has an agent: block but "agent" is not under uses:'
    if not isinstance(block, dict):
        return 'agent: a mapping (module, sends, calls, actions)'
    module = block.setdefault('module', 'agent.py')
    if not isinstance(module, str) or not re.match(r'^[a-z][a-z0-9_]{0,39}\.py$', module):
        return 'agent.module: a file name like agent.py'
    sends = block.setdefault('sends', {})
    if not isinstance(sends, dict):
        return 'agent.sends: a mapping of kind to {privacy: aggregate|device}'
    for kind, how in sends.items():
        if not KIND_RE.match(str(kind)):
            return f'agent.sends: bad kind {kind!r}'
        how = sends[kind] = how if isinstance(how, dict) else {}
        if how.setdefault('privacy', 'aggregate') not in PRIVACY:
            return f"agent.sends.{kind}: privacy must be {' or '.join(PRIVACY)}"
    targets = block.setdefault('targets', False)
    if targets is True:
        targets = block['targets'] = {'credentials': None}
    if isinstance(targets, dict):
        kinds = targets.setdefault('credentials', None)
        if kinds is not None and (not isinstance(kinds, list) or any(k not in CREDENTIAL_KINDS for k in kinds)):
            return f"agent.targets.credentials: some of {', '.join(CREDENTIAL_KINDS)}"
    elif targets is not False:
        return 'agent.targets: true, or {credentials: [ssh, ...]}, when the plugin works on inventory devices'
    for key in ('calls', 'actions'):
        names = block.setdefault(key, [])
        if not isinstance(names, list) or any(not isinstance(n, str) or not KIND_RE.match(n) for n in names):
            return f'agent.{key}: a list of names'
    known = {a.get('id') for a in m.get('actions') or [] if isinstance(a, dict)}
    for name in block['actions']:
        if name not in known:
            # An agent action is reached from one of the plugin's own actions: role check and audit.
            return f'agent.actions.{name}: add an action {name} to actions: (it runs it on the agent)'
    return ''


# ── privacy ──────────────────────────────────────────────────────────────────────────────

_V4 = re.compile(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?![\w.])')
_V6 = re.compile(r'(?<![\w:])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?:/\d{1,3})?(?![\w:])')
_MAC = re.compile(r'(?<![\w:.-])(?:[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}'
                  r'|[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4})(?![\w:.-])')


def _address_in(text):
    for m in _V4.finditer(text):
        try:
            ipaddress.ip_network(m.group(0), strict=False)
            return m.group(0)
        except ValueError:
            continue
    for m in _V6.finditer(text):
        try:
            ipaddress.ip_network(m.group(0), strict=False)
            return m.group(0)
        except ValueError:
            continue
    m = _MAC.search(text)
    return m.group(0) if m else None


def personal_data(value, _depth=0):
    """The first IP address, network or MAC address found anywhere in ``value`` (keys too), else
    None. Switch and port names (``sw-a-01|Gi1/0/1``), times and versions pass."""
    if _depth > 20:
        return '(nested too deep)'
    if isinstance(value, str):
        return _address_in(value) if any(c in value for c in '.:-') else None
    if isinstance(value, dict):
        for k, v in value.items():
            found = personal_data(k, _depth + 1) if isinstance(k, str) else None
            found = found or personal_data(v, _depth + 1)
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for v in value:
            found = personal_data(v, _depth + 1)
            if found:
                return found
    return None


def check_payload(spec_block, kind, payload):
    """Refuse what a plugin may not send: an unknown kind, or an address in an aggregate kind.
    Returns an error message or ''. Both the agent (before it sends) and the hosted side (when it
    takes it) check, so neither has to trust the other's version."""
    sends = (spec_block or {}).get('sends') or {}
    if kind not in sends:
        return f'the plugin does not list {kind!r} under agent.sends'
    if sends[kind].get('privacy', 'aggregate') == 'aggregate':
        found = personal_data(payload)
        if found:
            return f'{kind} is aggregate-only but holds an address ({_mask(found)})'
    return ''


def _mask(found):
    return found[:3] + '…' if len(found) > 3 else '…'


# ── the agent part ───────────────────────────────────────────────────────────────────────

class AgentPlugin:
    """Base class for a plugin's ``agent.py``. ``self.ctx`` is what the agent gives it.

    Override what you need:

    * ``start()``: open listeners, start threads (``self.ctx.thread(fn)``). Return quickly.
    * ``stop()``: the agent stops the plugin's threads and listeners itself; close anything else.
    * ``configure(settings)``: the hosted settings changed while it runs. The default restarts it.
    * ``check()``: one line for ``python -m floorbit_agent check``; raise PluginError when it can't work.
    * ``call_<name>(args)``, ``action_<name>(params)``: as listed in ``agent.calls`` / ``agent.actions``.
    """

    restart_on_configure = True

    def __init__(self, ctx):
        self.ctx = ctx

    @property
    def settings(self):
        return self.ctx.settings

    def log(self, msg):
        self.ctx.log(msg)

    def start(self):
        pass

    def stop(self):
        pass

    def configure(self, settings):
        """Called with the new settings; return True when the plugin took them without a restart."""
        return not self.restart_on_configure

    def check(self):
        return 'loaded'


class Health:
    """What one plugin says about itself: a status, a message, recent errors, a few numbers.
    Shared by the agent's context and MemoryContext so both report the same shape."""

    def __init__(self):
        self._lock = threading.Lock()
        self.status, self.message = 'ok', ''
        self.errors = deque(maxlen=ERRORS_KEPT)
        self.counters, self.gauges = {}, {}

    def set(self, status, message=''):
        if status not in STATUSES:
            raise PluginError(f"health status must be one of {', '.join(STATUSES)}")
        with self._lock:
            self.status, self.message = status, str(message)[:300]

    def error(self, message):
        with self._lock:
            self.errors.append({'at': time.time(), 'error': str(message)[:300]})

    def count(self, name, n=1):
        _metric_name(name)
        with self._lock:
            self.counters[name] = self.counters.get(name, 0) + n

    def gauge(self, name, value):
        _metric_name(name)
        with self._lock:
            self.gauges[name] = value

    def report(self):
        with self._lock:
            numbers = {**self.counters, **self.gauges}
            return {'status': self.status, 'message': self.message,
                    'metrics': dict(sorted(numbers.items())[:METRICS_KEPT]),
                    'errors': list(self.errors)}


def _metric_name(name):
    if not isinstance(name, str) or not KIND_RE.match(name):
        raise PluginError(f'bad metric name {name!r}: lowercase letters, digits and _')


class AuthBlocks:
    """Logins that failed, per device and credential: the plugin doesn't try them again until a
    tech clears them on the hosted side, so a wrong password never locks an account out or fills
    the AAA server with alarms. A new revision of the credential (edited password) is a new key.
    Kept in ``path`` (the plugin's state folder) when given, so a restart doesn't retry either."""

    MAX = 500

    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self.blocks = {}
        if path:
            try:
                with open(path, encoding='utf-8') as f:
                    raw = json.load(f)
                self.blocks = {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}
            except (OSError, ValueError):
                self.blocks = {}

    @staticmethod
    def _key(device, credential, rev):
        return f'{device}|{credential}|{rev}'

    def failed(self, device, credential, rev=None, message=''):
        """Returns True when this is new (worth saying), False when it was already blocked."""
        key = self._key(device, credential, rev)
        with self._lock:
            if key in self.blocks:
                return False
            if len(self.blocks) >= self.MAX:
                return False
            self.blocks[key] = {'device': str(device)[:120], 'credential': str(credential)[:120],
                                'rev': None if rev is None else str(rev)[:40], 'since': time.time(),
                                'message': str(message)[:300]}
            self._save()
        return True

    def may_login(self, device, credential, rev=None):
        with self._lock:
            return self._key(device, credential, rev) not in self.blocks

    def clear(self, device=None, credential=None):
        """Clear the blocks of a device (and credential); every one when both are None."""
        with self._lock:
            gone = [k for k, v in self.blocks.items()
                    if (device is None or v['device'] == str(device))
                    and (credential is None or v['credential'] == str(credential))]
            for k in gone:
                del self.blocks[k]
            if gone:
                self._save()
        return len(gone)

    def list(self):
        with self._lock:
            return sorted((dict(v) for v in self.blocks.values()), key=lambda b: b['since'])

    def _save(self):
        if not self.path:
            return
        try:
            with open(self.path + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(self.blocks, f)
            os.replace(self.path + '.tmp', self.path)
        except OSError:
            pass


class MemoryContext:
    """An agent context that keeps everything in memory: for plugin tests, and the reference for
    what the real one (floorbit_agent/plugin_host.py) offers."""

    def __init__(self, plugin_id='test', settings=None, spec_block=None, state_dir=None):
        self.id = plugin_id
        self.settings = dict(settings or {})
        self.spec_block = spec_block or {'sends': {}}
        self.state_dir = state_dir
        self.sent = []
        self.lines = []
        self.stopping = threading.Event()
        self.health_ = Health()
        self.auth = AuthBlocks()
        self._threads = []

    def log(self, message):
        self.lines.append(str(message))

    def auth_failed(self, device, credential, rev=None, message=''):
        if self.auth.failed(device, credential, rev, message):
            self.error(f'login to {device} with {credential} failed: {message}; not trying again until cleared')

    def may_login(self, device, credential, rev=None):
        return self.auth.may_login(device, credential, rev)

    def send(self, kind, payload):
        err = check_payload(self.spec_block, kind, payload)
        if err:
            raise PluginError(err)
        self.sent.append((kind, payload))

    def health(self, status, message=''):
        self.health_.set(status, message)

    def error(self, message):
        self.health_.error(message)
        self.log(message)

    def counter(self, name, n=1):
        self.health_.count(name, n)

    def gauge(self, name, value):
        self.health_.gauge(name, value)

    def thread(self, fn, name=None):
        t = threading.Thread(target=fn, name=name or f'plugin-{self.id}', daemon=True)
        self._threads.append(t)
        t.start()
        return t
