"""The floor plan template library (issue #48)."""
import base64

import pytest

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"1" * 32).decode()


@pytest.fixture
def plan(client):
    client.put("/api/halls/main/background", json={"image": PNG})
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 2})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 5, "y": 5}).get_json()
    # Event data on the device and the seats, which a template must never carry.
    client.patch(f"/api/inventory/{sw['id']}", json={"mgmt_ip": "192.0.2.10", "serial": "SN-SECRET", "notes": "x"})
    client.put("/api/seat-map/A-1", json={"ip": "198.51.100.9", "mac": "02:00:00:00:00:09", "nick": "player-nine"})
    return sw


def _save(client, **body):
    resp = client.post("/api/templates", json={"name": "Main layout", "description": "Spring event", **body})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_save_list_and_no_event_data(client, plan):
    t = _save(client)
    assert t["versions"] == [{"n": 1, "saved": t["created"], "halls": 1, "switches": 1, "seat_blocks": 1}]
    assert [x["name"] for x in client.get("/api/templates").get_json()["templates"]] == ["Main layout"]
    exported = client.get(f"/api/templates/{t['id']}/export")
    assert "attachment" in exported.headers["Content-Disposition"]
    text = exported.get_data(as_text=True)
    for secret in ("192.0.2.10", "SN-SECRET", "player-nine", "198.51.100.9", "02:00:00:00:00:09", "auth_"):
        assert secret not in text
    body = exported.get_json()
    assert body["format"] == "floorbit-template" and body["layout"]["halls"][0]["background"] == PNG
    assert body["layout"]["switches"] == [{"name": "sw-a-01", "role": "switch", "model": "", "x": 5.0, "y": 5.0,
                                           "hall_id": "main"}]


def test_rename_versions_duplicate_delete(client, plan):
    t = _save(client)
    assert client.patch(f"/api/templates/{t['id']}", json={"name": "  Spring  "}).get_json()["name"] == "Spring"
    assert client.patch(f"/api/templates/{t['id']}", json={"name": ""}).status_code == 400
    client.post("/api/seat-blocks", json={"name": "B", "x": 50, "y": 10, "cols": 2, "rows": 1})
    again = client.post(f"/api/templates/{t['id']}/versions", json={}).get_json()
    assert [(v["n"], v["seat_blocks"]) for v in again["versions"]] == [(1, 1), (2, 2)]
    assert len(client.get(f"/api/templates/{t['id']}/export?version=1").get_json()["layout"]["seat_blocks"]) == 1
    copy = client.post(f"/api/templates/{t['id']}/duplicate").get_json()
    assert copy["name"] == "Spring (copy)" and len(copy["versions"]) == 1
    assert client.delete(f"/api/templates/{t['id']}").status_code == 200
    assert [x["name"] for x in client.get("/api/templates").get_json()["templates"]] == ["Spring (copy)"]
    assert client.delete("/api/templates/../../data").status_code == 404


def test_start_from_a_template_replaces_the_plan(client, plan):
    t = _save(client)
    # Change everything, then go back.
    blocks = client.get("/api/seat-blocks").get_json()
    client.delete(f"/api/seat-blocks/{blocks[0]['id']}")
    client.post("/api/seat-blocks", json={"name": "Z", "x": 90, "y": 90})
    client.put(f"/api/switches/{plan['id']}", json={"x": 80, "y": 80})
    client.delete("/api/halls/main/background")
    result = client.post(f"/api/templates/{t['id']}/apply", json={}).get_json()
    assert result == {"halls": 1, "seat_blocks": 1, "switches_placed": 1, "switches_added": 0}
    assert [b["name"] for b in client.get("/api/seat-blocks").get_json()] == ["A"]
    sw = next(s for s in client.get("/api/switches").get_json() if s["id"] == plan["id"])
    assert (sw["x"], sw["y"]) == (5.0, 5.0)
    # The device kept its own data; the seat map is untouched.
    dev = next(d for d in client.get("/api/inventory").get_json()["devices"] if d["id"] == plan["id"])
    assert dev["mgmt_ip"] == "192.0.2.10"
    assert client.get("/api/halls").get_json()["halls"][0]["background"]


def test_one_hall_template_into_another_hall(client, plan):
    t = _save(client, hall="main")
    hall2 = client.post("/api/halls", json={"name": "Hall 2"}).get_json()["id"]
    clash = client.post(f"/api/templates/{t['id']}/apply", json={"hall": hall2})
    assert clash.status_code == 409 and "A" in clash.get_json()["error"]   # block names stay unique
    # Rename the main hall's block, then the template fits into hall 2.
    block = client.get("/api/seat-blocks").get_json()[0]
    client.put(f"/api/seat-blocks/{block['id']}", json={"name": "M"})
    result = client.post(f"/api/templates/{t['id']}/apply", json={"hall": hall2}).get_json()
    assert result["seat_blocks"] == 1
    assert [b["name"] for b in client.get(f"/api/seat-blocks?hall={hall2}").get_json()] == ["A"]
    assert [b["name"] for b in client.get("/api/seat-blocks?hall=main").get_json()] == ["M"]
    halls = {h["id"]: h for h in client.get("/api/halls").get_json()["halls"]}
    assert halls[hall2]["background"] and halls[hall2]["switches"] == 1 and halls["main"]["switches"] == 0


def test_import_strips_event_data(client, plan):
    t = _save(client)
    body = client.get(f"/api/templates/{t['id']}/export").get_json()
    body["layout"]["switches"][0]["mgmt_ip"] = "192.0.2.10"
    body["layout"]["seat_blocks"][0]["nick"] = "player-nine"
    body["layout"]["checkins"] = [{"seat": "A-1"}]
    body["accounts"] = {"admin": "hash"}
    resp = client.post("/api/templates/import", json=body)
    assert resp.status_code == 201
    assert resp.get_json()["dropped"] == ["accounts", "checkins", "mgmt_ip", "nick"]
    text = client.get(f"/api/templates/{resp.get_json()['id']}/export").get_data(as_text=True)
    assert "192.0.2.10" not in text and "player-nine" not in text and "checkins" not in text


@pytest.mark.parametrize("bad", [
    {"format": "floorbit-backup"},
    {"format": "floorbit-template", "version": 9},
    {"format": "floorbit-template", "version": 1, "layout": {"halls": []}},
    {"format": "floorbit-template", "version": 1, "layout": {"halls": [{"id": "h", "name": "H"}],
                                                             "seat_blocks": [{"name": "A", "x": 500, "y": 1}]}},
    {"format": "floorbit-template", "version": 1, "layout": {"halls": [{"id": "h", "name": "H",
                                                                        "background": "data:text/html;base64,PA=="}]}},
])
def test_bad_imports_are_refused(client, bad):
    assert client.post("/api/templates/import", json=bad).status_code == 400


def test_templates_need_floorplan_edit(anon_client, client, plan):
    t = _save(client)
    assert anon_client.post("/api/templates", json={"name": "x"}).status_code in (401, 403)
    assert anon_client.post(f"/api/templates/{t['id']}/apply", json={}).status_code in (401, 403)


def test_audit_log_names_the_template_actions(client, plan):
    t = _save(client)
    client.post(f"/api/templates/{t['id']}/apply", json={})
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert "Saved floor plan as template" in actions and "Started from template" in actions
