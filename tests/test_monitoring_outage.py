"""What seat lookups say while the agent or LibreNMS is away."""
from floorbit import sources
from integrations import checkin


class Silent:
    """A monitoring source that answers nothing: the agent is away."""
    def __init__(self):
        self.asked = 0

    def enabled(self):
        return True

    def resolve_ip(self, ip, device=None):
        self.asked += 1
        return None


def test_a_lookup_during_an_outage_says_try_again_not_unknown(client, monkeypatch):
    monkeypatch.setattr(sources, "monitoring", lambda: Silent())
    r = client.get("/api/resolve/192.0.2.10")
    assert r.status_code == 404                              # it asked and nobody knows the address
    sources.mark_failed("Local agent", "The local agent is not connected.")
    r = client.get("/api/resolve/192.0.2.10")
    assert r.status_code == 503 and r.get_json()["offline_since"]
    sources.mark_ok(None)


def test_a_check_in_tried_during_an_outage_is_not_remembered(monkeypatch):
    silent = Silent()
    monkeypatch.setattr(sources, "monitoring", lambda: silent)
    sources.mark_failed("Local agent", "The local agent is not connected.")
    assert checkin.port_of("192.0.2.10") is None
    sources.mark_ok(None)
    assert checkin.port_of("192.0.2.10") is None
    assert silent.asked == 2                                 # asked again once it was back
    assert checkin.port_of("192.0.2.10") is None and silent.asked == 2   # a real "unknown" is kept
