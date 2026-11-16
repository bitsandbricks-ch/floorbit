"""Where the server's own HTTP requests may go (issue #505). Only a local socket, no real service."""
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests

from floorbit import outbound


@pytest.fixture
def local_server(monkeypatch):
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(name, "*")   # straight to the socket, even where a proxy is set
    class Ok(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Ok)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def test_never_link_local_unspecified_or_multicast(monkeypatch):
    monkeypatch.delenv("OUTBOUND_BLOCK_NETS", raising=False)
    for addr in ("169.254.169.254", "fe80::1%eth0", "0.0.0.0", "::", "224.0.0.1", "ff02::1",
                 "::ffff:169.254.169.254", "64:ff9b::a9fe:a9fe", "2002:a9fe:a9fe::1"):
        assert outbound.refused(addr), addr
    for addr in ("127.0.0.1", "192.0.2.10", "10.0.0.5", "2001:db8::1", "64:ff9b::c000:20a"):
        assert outbound.refused(addr) is None, addr   # self-hosted: NetBox on the LAN is fine


def test_block_nets_refuse_more_for_a_hosted_floorbit(monkeypatch):
    monkeypatch.setenv("OUTBOUND_BLOCK_NETS", "127.0.0.0/8, ::1/128, 10.42.0.0/16, not-a-net")
    assert "OUTBOUND_BLOCK_NETS" in outbound.refused("127.0.0.1")
    assert outbound.refused("::1") and outbound.refused("10.42.3.4")
    assert outbound.refused("::ffff:10.42.3.4")          # the IPv4 it reaches is what counts
    assert outbound.refused("192.0.2.10") is None


def test_every_request_is_checked_where_it_connects(app_module, local_server, monkeypatch):
    # app_module has made the app, which installs the guard into urllib3.
    monkeypatch.delenv("OUTBOUND_BLOCK_NETS", raising=False)
    url = f"http://127.0.0.1:{local_server}/"
    assert requests.get(url, timeout=5).text == "ok"
    monkeypatch.setenv("OUTBOUND_BLOCK_NETS", "127.0.0.0/8")
    with pytest.raises(requests.ConnectionError, match="OUTBOUND_BLOCK_NETS"):
        requests.get(url, timeout=5)
    with pytest.raises(requests.ConnectionError, match="OUTBOUND_BLOCK_NETS"):
        requests.Session().get(url, timeout=5)        # sessions (the plugins' base) too


def test_a_name_is_checked_after_it_resolves(app_module, local_server, monkeypatch):
    # DNS rebinding: the name looked harmless when it was saved and now points somewhere else.
    real = socket.getaddrinfo

    def rebinding(host, *args, **kwargs):
        return real("127.0.0.1" if host == "netbox.example.com" else host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", rebinding)
    monkeypatch.setenv("OUTBOUND_BLOCK_NETS", "127.0.0.0/8")
    with pytest.raises(requests.ConnectionError, match="OUTBOUND_BLOCK_NETS"):
        requests.get(f"http://netbox.example.com:{local_server}/", timeout=5)
    monkeypatch.delenv("OUTBOUND_BLOCK_NETS")
    assert requests.get(f"http://netbox.example.com:{local_server}/", timeout=5).text == "ok"
