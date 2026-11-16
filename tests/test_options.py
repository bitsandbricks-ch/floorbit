"""GET /api/options/<kind>: the choices for fields that name something Floorbit knows, so no
switch, port or seat is ever typed in. Made-up names."""
from floorbit import sources


def test_switches_seats_and_blocks_come_from_the_plan(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 11, "rows": 1})
    client.post("/api/switches", json={"name": "sw-a-01", "x": 1, "y": 1})
    seats = [o["value"] for o in client.get("/api/options/seats").get_json()["options"]]
    assert seats[:3] == ["A-1", "A-2", "A-3"] and seats[-1] == "A-11"          # natural order
    assert "sw-a-01" in [o["value"] for o in client.get("/api/options/switches").get_json()["options"]]
    assert client.get("/api/options/blocks").get_json()["options"] == [{"value": "A", "label": "A", "hint": "11"}]
    assert client.get("/api/options/nope").status_code == 404


def test_ports_list_free_ones_first_and_say_who_holds_the_rest(client, monkeypatch):
    class Mon:
        def device_ports(self, host):
            return [{"name": f"Gi1/0/{n}"} for n in (10, 2, 1)]
    monkeypatch.setattr(sources, "monitoring", lambda: Mon())
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/2", "seat": "A-2"})
    opts = client.get("/api/options/ports?switch=sw-a-01").get_json()["options"]
    assert [(o["value"], o["used"]) for o in opts] == [("Gi1/0/1", None), ("Gi1/0/10", None), ("Gi1/0/2", "A-2")]
    assert client.get("/api/options/ports").get_json()["options"] == []


def test_every_list_answers(client):
    for kind in ("halls", "firewalls", "agents", "users", "teams"):
        r = client.get(f"/api/options/{kind}")
        assert r.status_code == 200 and isinstance(r.get_json()["options"], list), kind
