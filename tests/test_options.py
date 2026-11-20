"""GET /api/options/<kind>: the choices for fields that name something Floorbit knows, so no
switch, port or seat is ever typed in. Made-up names."""
from floorbit import sources


def test_switches_seats_and_blocks_come_from_the_plan(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 11, "rows": 1})
    client.post("/api/switches", json={"name": "sw-a-01", "x": 1, "y": 1})
    seats = [o["value"] for o in client.get("/api/options/seats").get_json()["options"]]
    assert seats[:3] == ["A-1", "A-2", "A-3"] and seats[-1] == "A-11"          # natural order
    assert "sw-a-01" in [o["value"] for o in client.get("/api/options/switches").get_json()["options"]]
    block = client.get("/api/seat-blocks").get_json()[0]
    assert client.get("/api/options/blocks").get_json()["options"] == [
        {"value": block["id"], "label": "A", "hint": "11"}]
    assert client.get("/api/options/nope").status_code == 404


def test_a_block_named_by_its_rows_is_offered_by_its_row_letters(client):
    """#1078: a block without a name of its own is named by its rows, and the picker lists it."""
    client.post("/api/seat-blocks", json={"name": "B", "x": 10, "y": 10, "cols": 2, "rows": 1})
    client.post("/api/seat-blocks", json={"name": "", "x": 60, "y": 10, "cols": 2, "rows": 2, "naming": "rows",
                                          "row_start": "C"})
    opts = client.get("/api/options/blocks").get_json()["options"]
    assert [(o["label"], o["hint"]) for o in opts] == [("B", "2"), ("C\u2013D", "4")]
    assert all(o["value"] for o in opts)


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


def test_a_port_the_source_lists_twice_is_offered_once(client, monkeypatch):
    """A picker can't hold one value twice (#972): igb0 once, its VLAN igb0.10 still apart."""
    class Mon:
        def device_ports(self, host):
            return [{"name": "igb0"}, {"name": "igb1"}, {"name": "igb0"}, {"name": "igb0.10"}]
    monkeypatch.setattr(sources, "monitoring", lambda: Mon())
    opts = client.get("/api/options/ports?switch=fw-01").get_json()["options"]
    assert [o["value"] for o in opts] == ["igb0", "igb0.10", "igb1"]

def test_every_list_answers(client):
    for kind in ("halls", "firewalls", "agents", "users", "teams"):
        r = client.get(f"/api/options/{kind}")
        assert r.status_code == 200 and isinstance(r.get_json()["options"], list), kind


def test_the_plan_names_each_row_as_the_row_picker_does(client):
    """#1078: a dashboard pane picks a row from the plan; ids and names match /api/options/rows."""
    client.post("/api/seat-blocks", json={"name": "", "x": 10, "y": 10, "cols": 3, "rows": 2, "naming": "rows",
                                          "row_start": "C"})
    client.post("/api/seat-blocks", json={"name": "A", "x": 50, "y": 10, "cols": 2, "rows": 2})
    shapes = client.get("/api/plan").get_json()["drawing"]["shapes"]
    from_plan = sorted((r["id"], r["label"]) for s in shapes for r in
                       [{"id": x["id"], "label": x["name"]} for x in s["row_list"]])
    options = sorted((o["value"], o["label"]) for o in client.get("/api/options/rows").get_json()["options"])
    assert from_plan == options and len(options) == 4
