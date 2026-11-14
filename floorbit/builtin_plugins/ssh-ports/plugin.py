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
        port = target.get('port') or ''
        if not PORT_RE.match(port):
            raise PluginError('Bad port name.')
        login = target.get('login') or {}
        if not login.get('username') or not login.get('password'):
            raise PluginError('This needs your switch login.')
        down, up = self.commands()
        wait = int(self.settings.get('down_seconds') or 5)
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
            self._run(shell, [c.format(port=port) for c in down], timeout)
            time.sleep(wait)
            self._run(shell, [c.format(port=port) for c in up], timeout)
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
        self.log(f'bounced {port} on {target["switch"]}')
        return {'message': f'{port} on {target["switch"]} was down for {wait} s and is back up.'}

    @staticmethod
    def _read(shell, timeout):
        out, deadline = '', time.monotonic() + timeout
        while time.monotonic() < deadline:
            if shell.recv_ready():
                out += shell.recv(65535).decode('utf-8', 'replace')
                if PROMPT_RE.search(out):
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
