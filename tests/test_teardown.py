"""Teardown checklist (issue #37)."""
import io
import zipfile

from tests.test_rbac import sign_in_as


def test_the_checklist_tracks_gear_configs_export_and_own_steps(client):
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5}).get_json()
    spare = client.post("/api/inventory", json={"name": "sw-spare-01", "role": "switch"}).get_json()
    client.post(f"/api/gear/{spare['id']}/out", json={"to": "tech-ana"})

    body = client.get("/api/teardown").get_json()
    assert body["done"] is False and body["left"] == 3   # gear out, one config, the export
    assert body["parts"]["gear"]["out"][0]["to"] == "tech-ana"

    client.post(f"/api/gear/{spare['id']}/in", json={})
    body = client.put(f"/api/teardown/switches/{sw['id']}", json={"done": True}).get_json()
    assert body["parts"]["configs"]["done"] and body["parts"]["gear"]["done"]

    step = client.post("/api/teardown/items", json={"text": "Return the rented switches"}).get_json()
    item = step["parts"]["custom"]["items"][0]
    assert step["left"] == 2
    assert client.post("/api/teardown/items", json={"text": "  "}).status_code == 400
    client.patch(f"/api/teardown/items/{item['id']}", json={"done": True})

    export = client.get("/api/teardown/export.zip")
    assert export.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(export.data)).namelist()
    assert sorted(names) == ["backup.json", "gear-history.csv", "handovers.json", "incidents.csv", "report.pdf"]
    body = client.get("/api/teardown").get_json()
    assert body["done"] is True and body["parts"]["export"]["last"]["by"]

    assert client.delete(f"/api/teardown/items/{item['id']}").status_code == 200
    assert client.delete(f"/api/teardown/items/{item['id']}").status_code == 404
    assert client.put("/api/teardown/switches/nope", json={"done": True}).status_code == 404


def test_leads_tick_but_only_admins_export(app_module, client):
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.get("/api/teardown").status_code == 200
    assert lead.post("/api/teardown/items", json={"text": "Sweep"}).status_code == 200
    assert lead.get("/api/teardown/export.zip").status_code == 403
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.get("/api/teardown").status_code == 403
