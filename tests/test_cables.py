"""Cables and patching (issue #97): switch port -> patch panel -> seat, labels, NetBox import."""
from floorbit import cables
from floorbit.builtin_plugins.netbox.plugin import cable as nb_cable
from tests.test_inventory import FakeHttp, FakeResponse, netbox_plugin
from tests.test_rbac import sign_in_as

ONE = {"switch": "sw-a-01", "port": "Gi1/0/3", "panel": "PP-A", "panel_port": "3", "seat": "a-3",
       "color": "blue", "length_m": "2.5"}


def test_add_change_delete(client):
    r = client.post("/api/cables", json=ONE)
    assert r.status_code == 201
    c = r.get_json()
    assert (c["label"], c["seat"], c["length_m"], c["source"]) == ("C-0001", "A-3", 2.5, "floorbit")
    # One cable per switch port, and labels are unique.
    assert client.post("/api/cables", json={**ONE, "port": "gi1/0/3"}).status_code == 409
    for bad in ({"port": "Gi1/0/4", "label": "c-0001"}, {"port": ""}, {"port": "Gi1/0/5", "panel_port": "5"},
                {"port": "Gi1/0/5", "length_m": "far"}, {"port": "Gi1/0/5", "length_m": 900}):
        assert client.post("/api/cables", json={"switch": "sw-a-01", **bad}).status_code == 400, bad
    two = client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/4", "seat": "A-4"}).get_json()
    assert two["label"] == "C-0002" and two["panel"] == ""

    changed = client.patch(f"/api/cables/{c['id']}", json={"seat": "A-5", "note": "moved"}).get_json()
    assert (changed["seat"], changed["note"], changed["label"]) == ("A-5", "moved", "C-0001")
    assert client.patch("/api/cables/nope", json={}).status_code == 404

    body = client.get("/api/cables?q=pp-a").get_json()
    assert [x["label"] for x in body["cables"]] == ["C-0001"]
    assert [x["label"] for x in client.get("/api/cables?seat=a-4").get_json()["cables"]] == ["C-0002"]

    csv = client.get("/api/cables.csv").data.decode()
    assert csv.splitlines()[0].startswith("label,switch,port") and "C-0002,sw-a-01,Gi1/0/4" in csv
    pdf = client.get(f"/api/cables/labels.pdf?ids={c['id']}")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")

    assert client.delete(f"/api/cables/{two['id']}").status_code == 200
    assert client.delete(f"/api/cables/{two['id']}").status_code == 404
    entries = client.get("/api/settings/audit?area=cables").get_json()["entries"]
    assert {e["action"] for e in entries} == {"Added cable", "Changed cable", "Removed cable"}
    assert any(e["target"].startswith("C-0001: sw-a-01 Gi1/0/3 > PP-A 3") for e in entries)


def test_labels_two_per_cable():
    rows = [{"id": f"x{i}", "label": f"C-{i:04d}", "switch": "sw-a-01", "port": f"Gi1/0/{i}", "seat": f"A-{i}"}
            for i in range(1, 14)]
    pdf = cables.labels_pdf(rows, "https://floor.example.com")
    # 26 labels: two pages of 3 x 8.
    assert pdf.startswith(b"%PDF") and b"/Count 2 " in pdf


def test_viewers_read_only(app_module, client):
    client.post("/api/cables", json=ONE)
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.get("/api/cables").status_code == 200
    assert viewer.post("/api/cables", json={"switch": "sw-b", "port": "Gi1/0/1"}).status_code == 403
    assert viewer.post("/api/cables/import").status_code == 403


def test_import_from_demo_keeps_crew_cables(client):
    # NetBox is on by default but not set up yet: its own message comes back.
    r = client.post("/api/cables/import")
    assert r.status_code == 502 and "NetBox URL" in r.get_json()["error"]
    mine = client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/1", "label": "MINE"}).get_json()
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    assert "Demo" in " ".join(client.get("/api/cables").get_json()["sources"])
    r = client.post("/api/cables/import").get_json()
    # The demo hall's A-1 is on sw-a-01 Gi1/0/1, which already has the crew's cable: that one stays.
    assert r["imported"] > 50 and any("skipped" in e for e in r["errors"])
    assert any("NetBox URL" in e for e in r["errors"])   # one source failing doesn't stop the others
    rows = client.get("/api/cables").get_json()["cables"]
    assert next(c for c in rows if c["port"] == "Gi1/0/1" and c["switch"] == "sw-a-01")["label"] == "MINE"
    imported = next(c for c in rows if c["source"] == "import")
    assert client.patch(f"/api/cables/{imported['id']}", json={"note": "x"}).status_code == 409
    # Importing again replaces the last import instead of doubling it.
    again = client.post("/api/cables/import").get_json()
    assert again["imported"] == r["imported"] and len(client.get("/api/cables").get_json()["cables"]) == len(rows)
    assert mine["id"] in {c["id"] for c in client.get("/api/cables").get_json()["cables"]}


NB4 = {"id": 7, "label": "", "color": "2196f3", "length": 300, "length_unit": {"value": "cm"},
       "description": "Seat: B-14",
       "a_terminations": [{"object_type": "dcim.frontport", "object": {"name": "12", "device": {"name": "PP-B"}}}],
       "b_terminations": [{"object_type": "dcim.interface",
                           "object": {"name": "Gi1/0/12", "device": {"name": "sw-b-02"}}}]}
NB3 = {"id": 8, "label": "K-8", "termination_a_type": "dcim.interface",
       "termination_a": {"name": "ge-0/0/1", "device": {"name": "sw-c-01"}},
       "termination_b_type": "dcim.interface", "termination_b": {"name": "eth0", "device": {"name": "ap-1"}}}


def test_netbox_cable_mapping_for_3_and_4():
    four = nb_cable(NB4)
    assert (four["label"], four["switch"], four["port"], four["panel"], four["panel_port"]) == \
        ("NB-7", "sw-b-02", "Gi1/0/12", "PP-B", "12")
    assert (four["seat"], four["color"], four["length_m"]) == ("B-14", "blue", 3.0)
    three = nb_cable(NB3)
    assert (three["label"], three["switch"], three["port"], three["panel"]) == ("K-8", "sw-c-01", "ge-0/0/1", "")
    power = {"id": 9, "a_terminations": [{"object_type": "dcim.powerport", "object": {"name": "PSU1"}}],
             "b_terminations": []}
    assert nb_cable(power) is None


def test_netbox_plugin_pages_cables(app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    http = FakeHttp({"/api/dcim/cables/": FakeResponse({"results": [NB4, NB3], "next": None})})
    assert [c["label"] for c in netbox_plugin(registry, http).cables()] == ["NB-7", "K-8"]
