"""SSH errors say why in words: the exception's type alone hides a closed port, a wrong name or no
route, and a session that breaks off after the login isn't "could not reach"."""
import errno
import importlib.util
import pathlib
import socket

import paramiko

PATH = pathlib.Path(__file__).resolve().parent.parent / "floorbit" / "builtin_plugins" / "ssh-ports" / "plugin.py"


def load():
    spec = importlib.util.spec_from_file_location("ssh_ports_plugin_for_errors", PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ssh_errors_name_the_cause():
    why = load()._why
    closed = paramiko.ssh_exception.NoValidConnectionsError({("192.0.2.21", 22): ConnectionRefusedError(
        errno.ECONNREFUSED, "Connection refused")})
    assert why(closed) == "nothing listens on the SSH port"
    assert why(socket.gaierror(-2, "Name or service not known")) == "the name does not resolve"
    assert why(OSError(errno.EHOSTUNREACH, "No route to host")) == "no route to it"
    assert why(EOFError()) == "the switch closed the connection"
    assert why(paramiko.SSHException("SSH session not active")) == "SSHException: SSH session not active"
