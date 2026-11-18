"""A saved API token only goes to the URL it was saved with: who may change settings never sees
the token (it is write-only), so pointing the URL at their own server must not hand it to them."""
import pytest

from floorbit import settings as settings_mod

OLD, NEW = "https://librenms.example.com", "https://attacker.example.net"


@pytest.fixture
def saved(client):
    resp = client.put("/api/settings", json={"librenms.url": OLD, "librenms.token": "token-example"})
    assert resp.status_code == 200, resp.data
    return client


def test_a_new_url_needs_the_token_again(saved):
    resp = saved.put("/api/settings", json={"librenms.url": NEW})
    assert resp.status_code == 400 and "token again" in resp.get_json()["error"]
    assert saved.get("/api/settings").get_json()["values"]["librenms.url"]["value"] == OLD
    resp = saved.put("/api/settings", json={"librenms.url": NEW, "librenms.token": ""})   # "keep it"
    assert resp.status_code == 400
    assert saved.put("/api/settings", json={"librenms.url": None}).status_code == 400   # back to env/default


def test_the_same_url_or_a_new_token_saves(saved):
    assert saved.put("/api/settings", json={"librenms.url": OLD + "/", "theme.name": "Example LAN"}).status_code == 200
    assert saved.put("/api/settings", json={"librenms.url": NEW, "librenms.token": "token-2"}).status_code == 200
    assert saved.put("/api/settings", json={"librenms.url": NEW, "librenms.token": None}).status_code == 200


def test_the_connection_test_does_not_send_the_saved_token_elsewhere(saved, monkeypatch):
    sent = []

    def get(url, **kwargs):
        sent.append(url)
        raise settings_mod.requests.ConnectionError("not in a test")
    monkeypatch.setattr(settings_mod.requests, "get", get)
    body = saved.post("/api/settings/test/librenms", json={"librenms.url": NEW}).get_json()
    assert body["ok"] is False and "token again" in body["message"] and sent == []
    saved.post("/api/settings/test/librenms", json={"librenms.url": OLD})
    assert sent and sent[0].startswith(OLD)


@pytest.fixture
def redirecting():
    """A LibreNMS address that redirects to another host, and what that host was sent."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    seen = []

    class Elsewhere(BaseHTTPRequestHandler):
        def do_GET(self):  # the name http.server asks for
            seen.append(self.headers.get("X-Auth-Token"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"system": [{"local_ver": "x"}], "devices": []}')

        def log_message(self, *args):
            pass

    class Redirecting(Elsewhere):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{other.server_port}{self.path}")
            self.end_headers()

    other, first = HTTPServer(("127.0.0.1", 0), Elsewhere), HTTPServer(("127.0.0.1", 0), Redirecting)
    for server in (other, first):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{first.server_port}", seen
    for server in (other, first):
        server.shutdown()
        server.server_close()


def test_a_redirect_does_not_take_the_token_to_another_host(client, redirecting):
    """requests drops only Authorization on a redirect to another host; X-Auth-Token went along."""
    from floorbit.builtin_plugins.librenms import breaker
    url, seen = redirecting
    body = client.post("/api/settings/test/librenms", json={"librenms.url": url, "librenms.token": "token-example"})
    assert body.get_json()["ok"] is False and "redirects to http://127.0.0.1" in body.get_json()["message"]
    breaker.reset()
    with pytest.raises(breaker.requests.HTTPError, match="redirects to http://127"):
        breaker.get(f"{url}/api/v0/devices", headers={"X-Auth-Token": "token-example"}, timeout=5)
    assert seen == []
