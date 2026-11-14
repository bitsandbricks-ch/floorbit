"""SSH port actions: take a switch port down and up again with the tech's own login.

The login arrives with each action and lives only as long as the one SSH connection. It is never
written to the plugin state, the log or an error message. Switch host keys are pinned on first
use (``trust_new_hosts``) and a changed key stops the action, since it can mean someone is in the
middle.
"""
import base64
import hashlib
import re
import time

import paramiko

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

PORT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/._:-]{0,47}$')
PROMPT_RE = re.compile(r'[>#%$\]]\s*$')
ERROR_RE = re.compile(r'%\s*(invalid|incomplete|ambiguous)|invalid input|syntax error|unknown command|^error:',
                      re.IGNORECASE | re.MULTILINE)
PLATFORMS = {
    'cisco_ios': (['configure terminal', 'interface {port}', 'shutdown', 'end'],
                  ['configure terminal', 'interface {port}', 'no shutdown', 'end']),
    'cisco_nxos': (['configure terminal', 'interface {port}', 'shutdown', 'end'],
                   ['configure terminal', 'interface {port}', 'no shutdown', 'end']),
    'aruba_aoscx': (['configure terminal', 'interface {port}', 'shutdown', 'end'],
                    ['configure terminal', 'interface {port}', 'no shutdown', 'end']),
    'aruba_procurve': (['configure', 'interface {port} disable', 'end'],
                       ['configure', 'interface {port} enable', 'end']),
    'juniper_junos': (['configure', 'set interfaces {port} disable', 'commit and-quit'],
                      ['configure', 'delete interfaces {port} disable', 'commit and-quit']),
}

# Turn the pager off so a long output isn't cut at "--More--".
PAGER_OFF = {'cisco_ios': 'terminal length 0', 'cisco_nxos': 'terminal length 0', 'aruba_aoscx': 'no page',
             'aruba_procurve': 'no page', 'juniper_junos': 'set cli screen-length 0'}


def clean_output(out, command):
    """What a command printed, without the echoed command and the prompt after it."""
    lines = out.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if lines and lines[0].strip().endswith(command.strip()):
        lines = lines[1:]
    if lines and PROMPT_RE.search(lines[-1]):
        lines = lines[:-1]
    return '\n'.join(lines).strip('\n')


def fingerprint(key):
    return f"{key.get_name()} SHA256:{base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')}"


class PinnedKeys(paramiko.MissingHostKeyPolicy):
    """Every connection lands here (no known_hosts file is loaded), so this decides alone."""

    def __init__(self, pinned, trust_new):
        self.pinned, self.trust_new, self.new = pinned, trust_new, None

    def missing_host_key(self, client, hostname, key):
        seen = fingerprint(key)
        known = self.pinned.get(hostname)
        if known and known != seen:
            raise PluginError(f'The SSH host key of {hostname} changed ({seen}). If the switch was replaced, '
                              'an admin can forget the pinned keys under Settings > Plugins.')
        if not known:
            if not self.trust_new:
                raise PluginError(f'{hostname} has no pinned host key and trusting new switches is off.')
            self.new = seen


class Plugin(Base):
    def commands(self):
        platform = self.settings.get('platform') or 'cisco_ios'
        if platform == 'custom':
            down, up = list(self.settings.get('custom_down') or []), list(self.settings.get('custom_up') or [])
            if not down or not up:
                raise PluginError('Custom needs both command lists under Settings > Plugins.')
            return down, up
        if platform not in PLATFORMS:
            raise PluginError(f'Unknown switch software {platform}.')
        return PLATFORMS[platform]

    # ports area -------------------------------------------------------------------------
    def port_login(self):
        return True

    def bounce_port(self, target):
        down, up = self.commands()
        wait = int(self.settings.get('down_seconds') or 5)
        self._session(target, [down, up], wait)
        self.log(f"bounced {target['port']} on {target['switch']}")
        return {'message': f"{target['port']} on {target['switch']} was down for {wait} s and is back up."}

    def set_port(self, target):
        down, up = self.commands()
        on = bool(target.get('enabled'))
        self._session(target, [up if on else down], 0)
        self.log(f"turned {target['port']} on {target['switch']} {'on' if on else 'off'}")
        return {'message': f"{target['port']} on {target['switch']} is {'on again' if on else 'shut'}."}

    def _session(self, target, batches, wait):
        """One SSH connection with the tech's login, running each batch of commands in turn."""
        port = target.get('port') or ''
        if not PORT_RE.match(port):
            raise PluginError('Bad port name.')

        def work(shell, timeout):
            for i, batch in enumerate(batches):
                if i:
                    time.sleep(wait)
                self._run(shell, [c.format(port=port) for c in batch], timeout)
        self._connect(target, work)

    # commands (issue #94) ---------------------------------------------------------------
    def command_platform(self):
        platform = self.settings.get('platform') or 'cisco_ios'
        return platform if platform in PLATFORMS else 'cisco_ios'

    def send_commands(self, target):
        """Run commands the core picked from a template; answer what the switch printed."""
        commands = [str(c) for c in target.get('commands') or []]
        if not commands or any('\n' in c or '\r' in c for c in commands):
            raise PluginError('No commands to run.')
        result = {'output': '', 'refused': None}

        def work(shell, timeout):
            pager = PAGER_OFF.get(self.command_platform())
            if pager:
                shell.send(pager + '\n')
                self._read(shell, timeout)
            parts = []
            for command in commands:
                shell.send(command + '\n')
                out = self._read(shell, timeout, settle=0.3)
                parts.append(clean_output(out, command))
                if ERROR_RE.search(out):
                    result['refused'] = command
                    break
            result['output'] = '\n\n'.join(parts)
        self._connect(target, work)
        self.log(f"ran {len(commands)} command(s) on {target['switch']}")
        return result

    def _connect(self, target, work):
        login = target.get('login') or {}
        if not login.get('username') or not login.get('password'):
            raise PluginError('This needs your switch login.')
        host = target['host']
        pinned = dict(self.ctx.state.get('hosts') or {})
        policy = PinnedKeys(pinned, self.settings.get('trust_new_hosts', True))
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(policy)
        timeout = int(self.settings.get('timeout') or 15)
        try:
            client.connect(host, port=int(self.settings.get('ssh_port') or 22), username=login['username'],
                           password=login['password'], timeout=timeout, banner_timeout=timeout,
                           auth_timeout=timeout, look_for_keys=False, allow_agent=False)
            if policy.new:
                pinned[host] = policy.new
                self.ctx.set_state('hosts', pinned)
                self.log(f'pinned the host key of {target["switch"]}: {policy.new}')
            shell = client.invoke_shell(width=200, height=1000)
            shell.settimeout(timeout)
            self._read(shell, timeout)
            work(shell, timeout)
        except PluginError:
            raise
        except paramiko.AuthenticationException:
            raise PluginError(f'{target["switch"]} refused the login.') from None
        except TimeoutError:
            raise PluginError(f'{target["switch"]} did not answer in time.') from None
        except (OSError, paramiko.SSHException) as exc:
            raise PluginError(f'Could not reach {target["switch"]} over SSH ({type(exc).__name__}).') from None
        finally:
            client.close()
            login.clear()

    @staticmethod
    def _read(shell, timeout, settle=0.0):
        """Read until the prompt. With ``settle``, the prompt must stay last that long: a long
        output can end a chunk on a "#" or ">" that isn't the prompt yet."""
        out, deadline, quiet_since = '', time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            if shell.recv_ready():
                out += shell.recv(65535).decode('utf-8', 'replace')
                quiet_since = time.monotonic() if PROMPT_RE.search(out) else None
                if quiet_since and not settle:
                    return out
            elif quiet_since and time.monotonic() - quiet_since >= settle:
                return out
            else:
                time.sleep(0.05)
        raise PluginError('The switch did not show a prompt in time.')

    def _run(self, shell, commands, timeout):
        for command in commands:
            shell.send(command + '\n')
            out = self._read(shell, timeout)
            if ERROR_RE.search(out):
                # The switch's own words, minus our command: never anything we sent as a login.
                raise PluginError(f'The switch refused "{command}": {out.strip().splitlines()[-2:][0][:120]}')

    # actions and endpoints --------------------------------------------------------------
    def run_forget_hosts(self, params):
        count = len(self.ctx.state.get('hosts') or {})
        self.ctx.set_state('hosts', {})
        return {'message': f'Forgot {count} pinned host key(s).'}

    def endpoint_hosts(self, args):
        return {'hosts': self.ctx.state.get('hosts') or {}}

    def test(self):
        down, _up = self.commands()
        return f"Takes a port down with: {'; '.join(down)}"
