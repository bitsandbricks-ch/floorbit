"""Find a player by nick, seat, IP or MAC (issue #14)."""
import pytest

from floorbit import seat_search, sources
from integrations import seat_sources

ARP = {"198.51.100.7": "02:00:00:00:00:07", "198.51.100.9": "02:00:00:00:00:09"}


class Monitoring:
    """ARP and port answers for 198.51.100.0/24, the way the LibreNMS plugin gives them."""

    def __init__(self, extra=None):
        self.arp = {**ARP, **(extra or {})}

    def enabled(self):
        return True

    def mac_for_ip(self, ip):
        return self.arp.get(ip)

    def ip_for_mac(self, mac):
        return next((ip for ip, m in self.arp.items() if m == mac), None)

    def resolve_ip(self, ip, search_device=None):
        if ip not in self.arp:
            return None
        return {"ip": ip, "mac": self.arp[ip], "hostname": "sw-a-01", "port": f"Gi1/0/{ip.rsplit('.', 1)[1]}"}


@pytest.fixture
def hall(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SEAT_SOURCES", "manual")   # only the hand mapping below, not the repo's seats.json
    seat_sources.invalidate()
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5}).get_json()
    client.put("/api/seat-map/A-2", json={"ip": "198.51.100.7", "nick": "player-two"})
    client.put("/api/seat-map/A-3", json={"mac": "02-00-00-00-00-09", "nick": "Player-Three"})
    client.put("/api/seat-map/A-4", json={"ip": "198.51.100.44", "nick": "someone"})
    monkeypatch.setattr(sources, "monitoring", lambda: Monitoring())
    return sw


@pytest.mark.parametrize("query, kind", [
    ("198.51.100.7", "ip"), ("2001:db8::1", "ip"), ("02:00:00:00:00:07", "mac"), ("0200.0000.0007", "mac"),
    ("player", "text"), ("A-2", "text"),
])
def test_what_a_query_is(query, kind):
    assert seat_search.kind_of(query)[0] == kind


def test_a_nick_finds_the_seat_and_its_block(client, hall):
    body = client.get("/api/seats/find?q=PLAYER").get_json()
    assert [(r["seat"], r["matched"]) for r in body["results"]] == [("A-2", "nick"), ("A-3", "nick")]
    assert body["results"][0]["block_id"]
    assert "port" not in body["results"][0]   # nick searches don't ask the switches


def test_an_ip_finds_the_seat_and_its_port(client, hall):
    [hit] = client.get("/api/seats/find?q=198.51.100.7").get_json()["results"]
    assert hit["seat"] == "A-2" and hit["matched"] == "ip"
    assert hit["switch"] == "sw-a-01" and hit["port"] == "Gi1/0/7" and hit["switch_id"] == hall["id"]


def test_a_mac_in_any_spelling(client, hall):
    [hit] = client.get("/api/seats/find?q=0200.0000.0009").get_json()["results"]
    assert hit["seat"] == "A-3" and hit["matched"] == "mac" and hit["port"] == "Gi1/0/9"


def test_arp_bridges_ip_and_mac(client, hall):
    # A-3 is only known by its MAC: its IP finds it through the ARP table.
    body = client.get("/api/seats/find?q=198.51.100.9").get_json()
    assert body["arp"] == "02:00:00:00:00:09" and body["results"][0]["seat"] == "A-3"
    # A-2 only by its IP: its MAC finds it the other way round.
    body = client.get("/api/seats/find?q=02:00:00:00:00:07").get_json()
    assert body["arp"] == "198.51.100.7" and body["results"][0]["seat"] == "A-2"


def test_an_address_without_a_seat_still_shows_its_port(client, hall, monkeypatch):
    monkeypatch.setattr(sources, "monitoring", lambda: Monitoring({"198.51.100.99": "02:00:00:00:00:99"}))
    [hit] = client.get("/api/seats/find?q=198.51.100.99").get_json()["results"]
    assert hit["seat"] is None and hit["port"] == "Gi1/0/99"


def test_finding_people_needs_seats_view(app_module, hall):
    app_module.app.extensions["auth"].users.add("watcher", "role-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "watcher", "password": "role-password-1"})
    assert viewer.get("/api/seats/find?q=player").status_code == 403
    assert app_module.app.test_client().get("/api/seats/find?q=player").status_code in (401, 403)
