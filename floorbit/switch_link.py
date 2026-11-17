"""Switch logins over the local agent: port actions, switch commands, config backups and the terminal.

The switches sit on the event network, so their SSH is opened by the agent there (Mike, 2026-11-17:
the agent is the only way Floorbit reaches the LAN). Everything around the connection stays here: who
may do it, the stored logins (opened for one call, floorbit/credentials.py), the audit log, the
cooldowns and the pinned host keys.

- ``call()`` runs one plugin method (``bounce_port``, ``set_port``, ``send_commands``) on the agent
  that serves the switch's hall. The login goes along for that one call only, over the agent's TLS
  link, and is cleared here as soon as the answer is back.
- ``open_shell()`` opens a terminal on the agent and returns an ``AgentShell``, which reads and
  writes it with long polls (``shell_io``), so floorbit/terminal.py works as with a local shell.
- **Host keys** are pinned here, in the plugin's state, and sent with each call: every agent (two in
  VRRP, a replaced one) checks a switch against the same key, and an admin forgets them in one place.

Without an agent, or for the demo plugin (it has no switches), the plugin is called right here.
"""
from __future__ import annotations

import contextlib

from . import agent_link
from .plugins import PluginError

LAN_METHODS = ('bounce_port', 'set_port', 'send_commands')
TIMEOUTS = {'bounce_port': 120, 'set_port': 60, 'send_commands': 90}
SHELL_WAIT = 10          # seconds the agent holds a read open when the switch is quiet
SHELL_OPEN_TIMEOUT = 45


def via_agent(spec):
    """Does this plugin's work go through the agent? Not the demo plugin: it has no switches."""
    return spec is not None and spec.id != 'demo' and agent_link.active()


def _wire(target, pinned):
    """What goes over the link: the target, the pinned key for its host, and the login's two fields."""
    login = target.get('login') or {}
    out = {k: v for k, v in target.items() if k != 'login'}
    out['login'] = {'username': login.get('username'), 'password': login.get('password')} if login else None
    out['pinned'] = pinned
    return out


def _pins(registry, spec):
    return dict(registry.state_of(spec.id).get('hosts') or {})


def _keep_pin(registry, spec, host, pin):
    """The agent saw this switch for the first time and trusted its key (``trust_new_hosts``)."""
    if not pin or not isinstance(pin, str) or len(pin) > 200:
        return
    state = dict(registry.state_of(spec.id))
    hosts = dict(state.get('hosts') or {})
    if hosts.get(host) == pin:
        return
    hosts[host] = pin
    state['hosts'] = hosts
    registry.save_state(spec.id, state)
    registry.log(spec.id, f'pinned the host key of {host} (seen by the local agent): {pin}')


def _agent_for(switch):
    try:
        return agent_link.agent_for(switch)
    except agent_link.AgentUnavailable as exc:
        raise PluginError(str(exc)) from None


def _ask(agent, method, args, timeout):
    try:
        return agent_link.tunnel.call(method, args, timeout=timeout, targets={agent})
    except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
        raise PluginError(str(exc)) from None


def call(registry, spec, method, target):
    """``registry.call(spec, method, target)``, on the agent when the switches are behind one."""
    if not via_agent(spec) or method not in LAN_METHODS:
        return registry.call(spec, method, target)
    wire = _wire(target, _pins(registry, spec).get(target.get('host')))
    try:
        agent = _agent_for(target.get('switch'))
        answer = _ask(agent, 'switch_call', [spec.id, method, wire], TIMEOUTS[method])
    finally:
        if wire.get('login'):
            wire['login'].clear()
    if not isinstance(answer, dict):
        raise PluginError('The local agent answered the switch call wrongly.')
    _keep_pin(registry, spec, target.get('host'), answer.get('pinned'))
    return answer.get('result')


def open_shell(registry, spec, target):
    """A shell for floorbit/terminal.py: the plugin's own, or one the agent holds open."""
    if not via_agent(spec):
        return registry.call(spec, 'open_shell', target)
    wire = _wire(target, _pins(registry, spec).get(target.get('host')))
    try:
        agent = _agent_for(target.get('switch'))
        answer = _ask(agent, 'shell_open', [spec.id, wire], SHELL_OPEN_TIMEOUT)
    finally:
        if wire.get('login'):
            wire['login'].clear()
    if not isinstance(answer, dict) or not isinstance(answer.get('id'), str):
        raise PluginError('The local agent answered the terminal call wrongly.')
    _keep_pin(registry, spec, target.get('host'), answer.get('pinned'))
    return AgentShell(agent, answer['id'])


class AgentShell:
    """A shell on the agent, with the interface floorbit/terminal.py reads: ``recv()`` gives '' while
    the switch is quiet and None once the shell is gone."""

    def __init__(self, agent, sid):
        self.agent, self.sid = agent, sid
        self.next = 0          # characters of output read so far
        self.gone = False

    def _io(self, data='', size=None, wait=0):
        answer = _ask(self.agent, 'shell_io', [self.sid, data, size, self.next, wait], wait + 15)
        if not isinstance(answer, dict):
            raise PluginError('The local agent answered the terminal call wrongly.')
        return answer

    def recv(self):
        if self.gone:
            return None
        try:
            answer = self._io(wait=SHELL_WAIT)
        except PluginError:
            # The agent dropped away or restarted: the shell it held is gone with it.
            self.gone = True
            return None
        data = str(answer.get('data') or '')
        self.next = int(answer.get('next') or self.next + len(data))
        if answer.get('closed') and not data:
            self.gone = True
            return None
        return data

    def send(self, data):
        self._io(data=data)

    def resize(self, cols, rows):
        self._io(size=[int(cols), int(rows)])

    def close(self):
        self.gone = True
        # The agent closes shells nobody reads on its own, so a failed close does no harm.
        with contextlib.suppress(PluginError):
            _ask(self.agent, 'shell_close', [self.sid], 10)
