"""One problem's page, and incidents made from a problem (issue #882)."""
import pytest

from floorbit import problems

pytestmark = pytest.mark.usefixtures("lan_here")


@pytest.fixture
def port_trouble(client, monkeypatch):
    sw = client.post("/api/inventory", json={"name": "sw-a-01", "role": "switch"}).get_json()
    item = {"id": "attention:errors:x", "kind": "errors", "level": "warn", "title": "Errors rising on Gi1/0/9",
            "where": "sw-a-01 Gi1/0/9", "since": 1, "link": "/plan?switch=sw-a-01", "switch_id": sw["id"]}
    monkeypatch.setattr(problems, "_attention", lambda: [dict(item)])
    return sw


def test_a_problem_has_a_page_with_its_device(client, port_trouble):
    body = client.get("/api/problems/attention:errors:x").get_json()
    assert body["problem"]["title"] == "Errors rising on Gi1/0/9"
    assert body["device"] == {"id": port_trouble["id"], "name": "sw-a-01"}
    assert body["problem"]["incident"] is None
    r = client.get("/api/problems/attention:errors:gone")
    assert r.status_code == 404 and "over" in r.get_json()["error"]


def test_an_incident_made_from_a_problem_links_back(client, port_trouble):
    r = client.post("/api/incidents", json={"switch_id": port_trouble["id"], "title": "Errors rising on Gi1/0/9",
                                            "from_problem": "attention:errors:x"})
    assert r.status_code == 201, r.get_json()
    made = r.get_json()
    assert made["from_problem"] == "attention:errors:x"
    assert client.get("/api/problems/attention:errors:x").get_json()["problem"]["incident"] == made["id"]
    listed = client.get("/api/problems").get_json()["attention"]
    assert listed[0]["incident"] == made["id"]
