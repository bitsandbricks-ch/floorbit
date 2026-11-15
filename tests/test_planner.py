"""Build planner (issue #34)."""
import io
import zipfile

from tests.test_rbac import sign_in_as


def _floor(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 100, "y": 100, "cols": 10, "rows": 5})   # 50 seats
    client.post("/api/seat-blocks", json={"name": "B", "x": 600, "y": 100, "cols": 4, "rows": 2})


def test_the_plan_splits_blocks_over_switches(client):
    _floor(client)
    plan = client.get("/api/planner").get_json()["plan"]
    names = [s["name"] for s in plan["switches"]]
    assert names == ["sw-a-01", "sw-a-02", "sw-b-01"]   # 46 usable ports: 50 seats need two switches
    a1 = plan["switches"][0]
    assert len(a1["ports"]) == 46
    assert a1["ports"][0] == {"n": 1, "name": "GigabitEthernet1/0/1", "seat": "A-1", "vlan": 100}
    assert [p["name"] for p in a1["uplinks"]] == ["GigabitEthernet1/1/1", "GigabitEthernet1/1/2"]
    assert len(plan["switches"][1]["ports"]) == 4 and plan["switches"][2]["vlan"] == 101
    assert plan["totals"] == {"seats": 58, "switches": 3, "new": 3, "vlans": 2, "uplinks": 6}

    change = {"spare": 0, "vlan_mode": "one", "mgmt_net": "198.51.100.0/24", "mgmt_gateway": "198.51.100.1"}
    assert client.put("/api/planner/settings", json=change).status_code == 200
    plan = client.get("/api/planner").get_json()["plan"]
    assert [s["mgmt_ip"] for s in plan["switches"]] == ["198.51.100.11", "198.51.100.12", "198.51.100.13"]
    assert {s["vlan"] for s in plan["switches"]} == {100}
    assert client.put("/api/planner/settings", json={"name": "switch"}).status_code == 400
    assert client.put("/api/planner/settings", json={"mgmt_net": "nope"}).status_code == 400
    assert client.put("/api/planner/settings", json={"spare": 48}).status_code == 400


def test_configs_labels_and_csv(client):
    _floor(client)
    cfg = client.get("/api/planner/config/sw-b-01").get_json()["config"]
    assert "hostname sw-b-01" in cfg and "description Seat B-8" in cfg and "switchport access vlan 101" in cfg
    z = zipfile.ZipFile(io.BytesIO(client.get("/api/planner/configs.zip").data))
    assert sorted(z.namelist()) == ["plan.csv", "sw-a-01.cfg", "sw-a-02.cfg", "sw-b-01.cfg"]
    csv = client.get("/api/planner/plan.csv").get_data(as_text=True)
    assert csv.splitlines()[1].startswith("sw-a-01,GigabitEthernet1/0/1,A-1,100,A,")
    labels = client.get("/api/planner/labels.pdf?block=B")
    assert labels.status_code == 200 and labels.data.startswith(b"%PDF")


def test_templates_are_sandboxed(client):
    _floor(client)
    bad = client.put("/api/planner/templates/evil", json={
        "label": "Evil", "access": "eth{n}", "uplink": "up{u}",
        "text": "{{ switch.__class__.__mro__[1].__subclasses__() }}"})
    assert bad.status_code == 200   # it compiles; rendering is where the sandbox stops it
    client.put("/api/planner/settings", json={"model": "evil"})
    resp = client.get("/api/planner/config/sw-b-01")
    assert resp.status_code == 400 and "failed" in resp.get_json()["error"]
    no_n = {"access": "eth", "uplink": "up{u}", "text": "x"}
    assert client.put("/api/planner/templates/x", json=no_n).status_code == 400
    broken = {"access": "eth{n}", "uplink": "up{u}", "text": "{% if %}"}
    assert client.put("/api/planner/templates/x", json=broken).status_code == 400
    ok = client.put("/api/planner/templates/mini", json={"label": "Mini", "access": "eth{n}", "uplink": "up{u}",
                                                          "text": "{{ switch.name }} {{ switch.ports|length }}"})
    assert ok.status_code == 200
    client.put("/api/planner/settings", json={"model": "mini"})
    assert client.get("/api/planner/config/sw-b-01").get_json()["config"] == "sw-b-01 8"
    assert client.delete("/api/planner/templates/mini").status_code == 200
    assert client.delete("/api/planner/templates/cisco-ios").status_code == 404


def test_apply_adds_only_missing_switches(client):
    _floor(client)
    client.post("/api/inventory", json={"name": "sw-a-01", "role": "switch"})
    added = client.post("/api/planner/apply").get_json()["added"]
    assert added == ["sw-a-02", "sw-b-01"]
    assert client.post("/api/planner/apply").get_json()["added"] == []
    devices = {d["name"]: d for d in client.get("/api/inventory").get_json()["devices"]}
    assert devices["sw-b-01"]["status"] == "planned" and devices["sw-b-01"]["x"] == 560


def test_planner_is_for_leads(app_module, client):
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.get("/api/planner").status_code == 403
    assert tech.post("/api/planner/apply").status_code == 403
