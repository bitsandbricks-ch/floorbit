"""Feature switches (issue #114)."""
from floorbit import features
from tests.test_rbac import sign_in_as


def test_a_feature_that_is_off_is_gone_and_back_when_on(client):
    assert client.get("/api/features").get_json() == {"off": []}
    assert client.get("/api/power").status_code == 200

    body = client.put("/api/settings/features", json={"power": False}).get_json()
    assert next(f for f in body["features"] if f["id"] == "power")["on"] is False
    assert client.get("/api/features").get_json() == {"off": ["power"]}
    answer = client.get("/api/power")
    assert answer.status_code == 404 and answer.get_json()["error"] == "This feature is turned off."
    assert client.get("/power").status_code == 404
    assert "/power" not in {p["href"] for p in client.get("/api/pages").get_json()["pages"]}   # sidebar and Go to

    entries = client.get("/api/settings/audit").get_json()["entries"]
    assert entries[0]["action"] == "Turned features on or off" and entries[0]["target"] == "power off"

    client.put("/api/settings/features", json={"power": True})
    assert client.get("/api/power").status_code == 200
    assert "/power" in {p["href"] for p in client.get("/api/pages").get_json()["pages"]}


def test_features_need_the_ones_they_build_on(client):
    client.put("/api/settings/features", json={"incidents": False})
    assert {"incidents", "helpdesk", "dispatch", "handover"} <= set(client.get("/api/features").get_json()["off"])
    assert client.get("/api/handover").status_code == 404
    assert client.get("/help/A1").status_code == 404     # the helpdesk page is public: still gone
    assert client.get("/api/helpdesk/seats/A1").status_code == 404
    # The live stream and the past events' neighbours are not caught by a prefix.
    assert features.owner("/api/events") is None and features.owner("/healthz") is None
    assert features.owner("/api/checkins") is None


def test_bad_changes_and_the_server_switch(client, monkeypatch):
    assert client.put("/api/settings/features", json={"nope": False}).status_code == 400
    assert client.put("/api/settings/features", json={"power": "off"}).status_code == 400
    assert client.put("/api/settings/features", json={}).status_code == 400

    monkeypatch.setenv(features.ENV, "traffic, ports")
    # Switch commands, the terminal and config backups need port actions, so they go off with them.
    assert set(client.get("/api/features").get_json()["off"]) == {"traffic", "ports", "commands", "terminal", "configs"}
    refused = client.put("/api/settings/features", json={"traffic": True})
    assert refused.status_code == 400 and features.ENV in refused.get_json()["error"]
    assert client.get("/api/flows").status_code == 404


def test_only_admins_switch_features(app_module):
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.get("/api/features").status_code == 200
    assert lead.get("/api/settings/features").status_code == 403
    assert lead.put("/api/settings/features", json={"power": False}).status_code == 403


def test_the_netflow_collector_keeps_nothing_while_traffic_is_off(app_module, monkeypatch):
    from floorbit.flows.collector import Collector
    monkeypatch.setenv(features.ENV, "traffic")
    collector = Collector(log=lambda _m: None)
    assert collector.enabled(now=0) is False
    monkeypatch.delenv(features.ENV)
    assert collector.enabled(now=1) is False   # asked again only every half minute
    assert collector.enabled(now=100) is True


def test_settings_pages_and_tools_are_in_the_sidebar_only_when_on(client):
    # Issue #236 put the links in a card; now the sidebar lists them, like on every crew page.
    hrefs = {p["href"] for p in client.get("/api/pages").get_json()["pages"]}
    assert {"/settings/users", "/handover"} <= hrefs

    client.put("/api/settings/features", json={"handover": False})
    assert "/handover" not in {p["href"] for p in client.get("/api/pages").get_json()["pages"]}
    client.put("/api/settings/features", json={"handover": True})
