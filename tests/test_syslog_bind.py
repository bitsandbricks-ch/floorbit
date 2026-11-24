import socket
import threading

from floorbit import syslog
from tests.test_syslog import _free_port


def test_a_tcp_port_that_is_taken_leaves_nothing_half_open(tmp_path, monkeypatch, lan_here):
    """UDP binds, TCP doesn't: start() reports it and stop() returns (it waited forever, #1145)."""
    port = _free_port()
    taken = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    taken.bind(("127.0.0.1", port))
    taken.listen()
    monkeypatch.setenv("SYSLOG_ENABLED", "1")
    monkeypatch.setenv("SYSLOG_TCP", "1")
    monkeypatch.setenv("SYSLOG_PORT", str(port))
    monkeypatch.setenv("SYSLOG_BIND", "127.0.0.1")
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    try:
        r.start()
        assert r.listening is None and "Can't listen" in r.error
        done = threading.Thread(target=r.stop, daemon=True)
        done.start()
        done.join(5)
        assert not done.is_alive()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
            u.bind(("127.0.0.1", port))                       # the UDP port was given back
    finally:
        taken.close()
