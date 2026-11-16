"""Crew notice (issue #246)."""
from floorbit import notice
from tests.test_rbac import sign_in_as


def test_put_up_read_and_take_down(client):
    assert client.get("/api/notice").get_json() == {"notice": None}
    assert client.put("/api/notice", json={"text": "  "}).status_code == 400
    assert client.put("/api/notice", json={"text": "x" * 281}).status_code == 400
    assert client.put("/api/notice", json={"text": "x", "level": "boom"}).status_code == 400
    assert client.put("/api/notice", json={"text": "x", "hours": 1000}).status_code == 400
    assert client.put("/api/notice", json={"text": "x", "hours": True}).status_code == 400

    up = client.put("/api/notice", json={"text": "Hall B: power work at 14:00,\n leave row C alone",
                                         "level": "warn", "hours": 2}).get_json()["notice"]
    assert up["text"] == "Hall B: power work at 14:00, leave row C alone"
    assert up["level"] == "warn" and up["until"] - up["at"] == 7200
    assert client.get("/api/notice").get_json()["notice"]["text"] == up["text"]
    entries = client.get("/api/settings/audit?area=incidents").get_json()["entries"]
    assert entries[0]["action"] == "Put up a crew notice"

    assert client.delete("/api/notice").get_json() == {"notice": None}
    assert client.get("/api/notice").get_json() == {"notice": None}


def test_an_expired_notice_is_gone():
    assert notice.current({"crew_notice": {"text": "old", "until": 100}}, now=101) is None
    assert notice.current({"crew_notice": {"text": "open", "until": None}}, now=101)["text"] == "open"


def test_everyone_reads_leads_write(app_module, client):
    client.put("/api/notice", json={"text": "Doors open at 18:00"})
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.get("/api/notice").get_json()["notice"]["text"] == "Doors open at 18:00"
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.put("/api/notice", json={"text": "mine"}).status_code == 403
    assert tech.delete("/api/notice").status_code == 403
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.put("/api/notice", json={"text": "Lead here"}).get_json()["notice"]["by"]


def test_the_floor_plan_has_a_place_for_it(client):
    page = client.get("/editor/classic").get_data(as_text=True)
    assert 'id="crew-notice"' in page and "/static/js/editor/notice.js" in page
