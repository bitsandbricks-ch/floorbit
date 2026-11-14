"""Gear loans (issue #36)."""
from tests.test_rbac import sign_in_as


def test_check_out_and_in(client):
    spare = {"name": "sw-spare-01", "role": "switch", "serial": "EXAMPLE123"}
    sw = client.post("/api/inventory", json=spare).get_json()
    ap = client.post("/api/inventory", json={"name": "ap-hall2-01", "role": "access-point"}).get_json()
    body = client.get("/api/gear").get_json()
    assert {i["name"]: i["loan"] for i in body["items"]} == {"sw-spare-01": None, "ap-hall2-01": None}

    assert client.post(f"/api/gear/{sw['id']}/out", json={"to": ""}).status_code == 400
    out = client.post(f"/api/gear/{sw['id']}/out", json={"to": "tech-ana", "note": "for row C"})
    assert out.status_code == 200 and out.get_json()["kind"] == "person"
    assert client.post(f"/api/gear/{sw['id']}/out", json={"to": "someone else"}).status_code == 409
    client.post(f"/api/gear/{ap['id']}/out", json={"to": "Hall 2 stage", "kind": "area"})
    items = {i["name"]: i["loan"] for i in client.get("/api/gear").get_json()["items"]}
    assert items["sw-spare-01"]["to"] == "tech-ana" and items["ap-hall2-01"]["kind"] == "area"

    back = client.post(f"/api/gear/{sw['id']}/in", json={})
    assert back.get_json()["returned_from"] == "tech-ana"
    assert client.post(f"/api/gear/{sw['id']}/in", json={}).status_code == 409
    assert client.post("/api/gear/nope/out", json={"to": "x"}).status_code == 404
    log = client.get("/api/gear").get_json()["log"]
    assert [(e["name"], e["action"]) for e in log] == [
        ("sw-spare-01", "in"), ("ap-hall2-01", "out"), ("sw-spare-01", "out")]
    assert "out_for" in log[0]
    entries = client.get("/api/settings/audit?area=gear").get_json()["entries"]
    assert {e["action"] for e in entries} == {"Checked out gear", "Checked in gear"}

    pdf = client.get("/api/gear/labels.pdf?role=switch")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_gear_is_for_the_crew(app_module, client):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.get("/api/gear").status_code == 403
    tech = sign_in_as(app_module, "te1", "tech")
    sw = client.post("/api/inventory", json={"name": "sw-x", "role": "switch"}).get_json()
    assert tech.post(f"/api/gear/{sw['id']}/out", json={"to": "te1"}).status_code == 200
