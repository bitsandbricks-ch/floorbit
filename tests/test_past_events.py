"""Past events and comparing them (issue #38)."""
import json

from tests.test_rbac import sign_in_as


def test_closing_an_event_archives_it_and_starts_the_next(client):
    client.put("/api/settings", json={"theme.name": "Example LAN 2026"})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5}).get_json()
    spare = client.post("/api/inventory", json={"name": "sw-spare-01", "role": "switch"}).get_json()
    client.post(f"/api/gear/{spare['id']}/out", json={"to": "tech-ana"})
    client.post("/api/teardown/items", json={"text": "Return the rented switches"})
    item = client.get("/api/teardown").get_json()["parts"]["custom"]["items"][0]
    client.patch(f"/api/teardown/items/{item['id']}", json={"done": True})
    client.put(f"/api/teardown/switches/{sw['id']}", json={"done": True})
    client.post("/api/incidents", json={"title": "No link", "switch_id": sw["id"]})

    body = client.get("/api/past-events").get_json()
    assert body["archived"] == []
    assert body["current"]["name"] == "Example LAN 2026" and body["current"]["figures"]["incidents"] == 1

    # The name has to be typed, so a stray click can't close the event.
    assert client.post("/api/past-events/close", json={"confirm": "wrong"}).status_code == 400
    closed = client.post("/api/past-events/close",
                         json={"confirm": "example lan 2026", "next_name": "Example LAN 2027"})
    assert closed.status_code == 200
    saved = closed.get_json()["archived"]
    assert saved["name"] == "Example LAN 2026" and saved["figures"]["incidents"] == 1

    body = client.get("/api/past-events").get_json()
    assert body["current"]["name"] == "Example LAN 2027"
    assert body["current"]["figures"]["incidents"] == 0
    assert [e["id"] for e in body["archived"]] == [saved["id"]]

    # The floor plan, the gear still out and the lead's own steps carry over, unticked.
    assert client.get("/api/incidents").get_json()["incidents"] == []
    teardown = client.get("/api/teardown").get_json()["parts"]
    assert teardown["custom"]["items"][0]["text"] == "Return the rented switches"
    assert not teardown["custom"]["items"][0]["done_at"] and not teardown["configs"]["done"]
    assert teardown["gear"]["out"][0]["to"] == "tech-ana"
    assert client.get("/api/gear").get_json()["log"] == []

    pdf = client.get(f"/api/past-events/{saved['id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    backup = json.loads(client.get(f"/api/past-events/backup/{saved['id']}.json").data)
    assert backup["format"] == "floorbit-backup"
    assert any(d.get("name") == "sw-a-01" for d in backup["layout"]["inventory"])

    assert client.patch(f"/api/past-events/{saved['id']}", json={"name": "Example LAN spring"}).get_json()["name"] \
        == "Example LAN spring"
    assert client.patch(f"/api/past-events/{saved['id']}", json={"name": " "}).status_code == 400
    assert client.delete(f"/api/past-events/{saved['id']}").status_code == 200
    assert client.get("/api/past-events").get_json()["archived"] == []


def test_ids_are_checked_and_only_admins_close_or_download(app_module, client):
    assert client.get("/api/past-events/..%2Fdata/report.pdf").status_code == 404
    assert client.get("/api/past-events/20260101-zzzzzzzz/report.pdf").status_code == 404
    assert client.delete("/api/past-events/20260101-00000000").status_code == 404

    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.get("/api/past-events").status_code == 200
    assert lead.post("/api/past-events/close", json={"confirm": "close"}).status_code == 403
    assert lead.get("/api/past-events/backup/20260101-00000000.json").status_code == 403


def test_no_two_routes_answer_the_same_request(app_module):
    # /api/events is the live stream; a page's API took that path once and silently replaced it.
    seen = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            key = (method, rule.rule)
            assert key not in seen, f"{method} {rule.rule} is both {seen[key]} and {rule.endpoint}"
            seen[key] = rule.endpoint
