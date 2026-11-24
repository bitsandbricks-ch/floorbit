"""Each problem names the switch it is on, so the page can group by it (issue #883)."""
import pytest

from floorbit import problems

pytestmark = pytest.mark.usefixtures("lan_here")


def test_a_problem_names_its_switch_and_one_without_stays_without(client, monkeypatch):
    sw = client.post("/api/inventory", json={"name": "sw-a-01", "role": "switch"}).get_json()
    monkeypatch.setattr(problems, "_attention", lambda: [
        {"id": "attention:errors:x", "kind": "errors", "level": "warn", "title": "Errors rising on Gi1/0/9",
         "where": "sw-a-01 Gi1/0/9", "since": 1, "link": "", "switch_id": sw["id"]},
    ])
    monkeypatch.setattr(problems, "_forecast", lambda: [
        {"id": "forecast:1", "kind": "forecast", "level": "warn", "title": "Bandwidth", "where": "", "since": None,
         "link": "/stats"},
    ])
    body = client.get("/api/problems").get_json()
    assert body["attention"][0]["device"] == "sw-a-01"
    assert next(p for p in body["problems"] if p["kind"] == "forecast")["device"] is None
