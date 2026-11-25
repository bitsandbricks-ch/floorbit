"""An incident made from a problem hears when that problem ends (issue #882)."""
import pytest

from floorbit import incidents, problem_watch, problems
from tests.test_incidents import floor  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("lan_here", "floor")

PORT = {"id": "attention:errors:s1:Gi1/0/1", "kind": "errors", "level": "warn", "title": "Errors rising on Gi1/0/1",
        "where": "sw-a-01 Gi1/0/1", "since": 1, "link": "", "seat": "A-1"}


@pytest.fixture
def trouble(monkeypatch):
    live = {"on": True}
    monkeypatch.setattr(problems, "_attention", lambda: [dict(PORT)] if live["on"] else [])
    return live


def _incident(client):
    r = client.post("/api/incidents", json={"seat": "A-1", "title": PORT["title"], "from_problem": PORT["id"]})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def test_the_incident_is_marked_when_its_problem_ends_and_again_when_it_comes_back(client, app_module, trouble):
    iid = _incident(client)
    with app_module.app.app_context():
        assert problem_watch.tick(now=1000) == []
        trouble["on"] = False
        assert problem_watch.tick(now=2000) == [iid]
        assert incidents.get(iid)["problem_over_at"] == 2000
        assert problem_watch.tick(now=3000) == []      # marked once
        trouble["on"] = True
        assert problem_watch.tick(now=4000) == [iid]
        assert "problem_over_at" not in incidents.get(iid)


def test_a_fixed_incident_is_left_alone(client, app_module, trouble):
    iid = _incident(client)
    assert client.patch(f"/api/incidents/{iid}", json={"status": "fixed"}).status_code == 200
    trouble["on"] = False
    with app_module.app.app_context():
        assert problem_watch.tick(now=2000) == []
    assert "problem_over_at" not in incidents.get(iid)
