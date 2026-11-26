"""The tenant's own traffic categories (issue #1622): kept per tenant, used by applications, rule
sources, the flow classifier and the dashboard, with "other" for an id the tenant doesn't have."""
import json

import pytest

from floorbit import applications, traffic_categories
from floorbit.dashboard_core import traffic_mix_widget
from floorbit.flows.classify import Classifier, RuleError, compile_rules
from tests.test_ports import audit_lines, sign_in

ESPORTS = {"id": "esports", "name": "Esports", "name_de": "E-Sport", "colour": "#dc2626"}


def put(client, *cats):
    return client.put("/api/traffic/categories", json={"categories": list(cats)})


def test_own_categories_come_after_the_built_in_ones(app_module, client):
    resp = put(client, ESPORTS)
    assert resp.status_code == 200, resp.get_json()
    cats = client.get("/api/traffic/categories").get_json()["categories"]
    assert [c["id"] for c in cats] == [*traffic_categories.BUILTIN_IDS, "esports"]
    assert cats[-1] == {**ESPORTS, "builtin": False}
    actions = [(e["action"], e.get("target")) for e in audit_lines()]
    assert ("Added a traffic category", "Esports") in actions
    put(client, {**ESPORTS, "name": "E-sports"})
    put(client)
    actions = [e["action"] for e in audit_lines()]
    assert "Changed a traffic category" in actions and "Removed a traffic category" in actions


@pytest.mark.parametrize("bad", [
    {**ESPORTS, "id": "gaming"}, {**ESPORTS, "id": "Bad Id"}, {**ESPORTS, "name": ""},
    {**ESPORTS, "colour": "#123456"}, {**ESPORTS, "name": "Gaming"}, "esports",
])
def test_broken_categories_are_refused(app_module, client, bad):
    assert put(client, bad).status_code == 400
    assert traffic_categories.own() == []


def test_only_admins_change_them(app_module):
    viewer = sign_in(app_module, "watcher", "viewer")
    assert viewer.get("/api/traffic/categories").status_code == 200
    assert viewer.put("/api/traffic/categories", json={"categories": [ESPORTS]}).status_code == 403


def test_applications_use_own_categories_and_fall_back_to_other(app_module, client):
    resp = client.post("/api/applications", json={"name": "Example Cup", "kind": "game", "category": "esports"})
    assert resp.status_code == 400                       # not a category yet
    put(client, ESPORTS)
    cup = client.post("/api/applications", json={"name": "Example Cup", "kind": "game", "category": "esports",
                                                  "cidr": ["198.51.100.0/28"]}).get_json()
    assert cup["category"] == "esports"
    # A built-in one can be filed under an own category too, and keeps what it shipped.
    valorant = client.put("/api/applications/valorant", json={"category": "esports"}).get_json()
    assert valorant["category"] == "esports" and valorant["builtin"]
    rules = {r["name"]: r["category"] for r in applications.flow_rules()}
    assert rules["Example Cup"] == "esports"
    put(client)                                          # the category goes: its applications count as other
    apps = {a["id"]: a for a in applications.listing()}
    assert apps[cup["id"]]["category"] == "other" and apps["valorant"]["category"] == "other"


def test_an_import_with_a_category_this_tenant_lacks_counts_as_other(app_module, client):
    raw = json.dumps({"version": 1, "applications": [
        {"id": "example-arena", "name": "Example Arena", "kind": "game", "category": "esports",
         "sites": ["arena.example.com"]}]})
    assert client.post("/api/applications/import", json={"file": raw}).status_code == 200
    assert {a["id"]: a for a in applications.listing()}["example-arena"]["category"] == "other"


def test_the_classifier_takes_own_categories_only_from_applications():
    classifier = Classifier(compile_rules([{"name": "Web", "category": "web", "ports": ["tcp/443"]}]))
    classifier.set_applications([{"name": "Example Cup", "category": "esports", "cidr": ["198.51.100.0/28"]}])
    assert classifier("198.51.100.3", 6, 443, 50000) == ("Example Cup", "esports")
    with pytest.raises(RuleError):
        compile_rules([{"name": "x", "category": "esports"}])


def test_traffic_by_kind_shows_own_categories_with_their_colour(app_module, client):
    put(client, ESPORTS)
    w = traffic_mix_widget("de", {"mix_hour": {"gaming": 3_000_000_000, "esports": 1_000_000_000, "gone": 500}})
    assert [(i["label"], i["colour"]) for i in w["items"]] == [
        ("Gaming", "#16a34a"), ("Anderes", "#94a3b8"), ("E-Sport", "#dc2626")]
