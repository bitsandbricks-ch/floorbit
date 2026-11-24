"""Known inventory properties with types (issue #879, floorbit/property_catalog.py)."""
import pytest

from floorbit import property_catalog
from floorbit.inventory_scope import ScopeError


def _catalog(client):
    return {p["key"]: p for p in client.get("/api/inventory/properties").get_json()["properties"]}


def test_floorbits_own_properties_are_known_with_types(client):
    known = _catalog(client)
    assert known["telemetry.verify_tls"]["type"] == "bool" and known["telemetry.verify_tls"]["builtin"]
    assert known["telemetry.snmp.fdb"]["choices"] == ["qbridge", "cisco_vlans", "bridge", "off"]
    assert known["telemetry.drivers"]["type"] == "list"


def test_a_known_property_is_checked_and_an_unknown_one_kept(client):
    group = client.post("/api/inventory/groups", json={"name": "Core"}).get_json()
    url = f"/api/inventory/groups/{group['id']}"
    r = client.patch(url, json={"properties": {"telemetry.snmp.port": "abc"}})
    assert r.status_code == 400 and "number" in r.get_json()["error"]
    r = client.patch(url, json={"properties": {"telemetry.verify_tls": "No", "telemetry.drivers": "SNMP traps",
                                               "rack": "R1 left"}})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["properties"] == {"telemetry.verify_tls": "false", "telemetry.drivers": "snmp, traps",
                                          "rack": "R1 left"}
    r = client.patch(url, json={"properties": {"telemetry.snmp.fdb": "magic"}})
    assert r.status_code == 400 and "qbridge" in r.get_json()["error"]


def test_admins_define_their_own(client):
    r = client.post("/api/inventory/properties", json={"key": "PoE.Budget", "label": "PoE budget", "type": "number",
                                                       "unit": "W", "roles": ["switch"]})
    assert r.status_code == 201 and r.get_json()["key"] == "poe.budget"
    assert client.post("/api/inventory/properties", json={"key": "poe.budget"}).status_code == 409
    assert client.post("/api/inventory/properties", json={"key": "telemetry.x"}).status_code == 400
    assert client.post("/api/inventory/properties", json={"key": "side", "type": "choice"}).status_code == 400
    assert client.post("/api/inventory/properties", json={"key": "x", "roles": ["toaster"]}).status_code == 400
    assert _catalog(client)["poe.budget"]["unit"] == "W"
    assert client.patch("/api/inventory/defaults", json={"properties": {"poe.budget": "lots"}}).status_code == 400
    assert client.patch("/api/inventory/defaults", json={"properties": {"poe.budget": "370"}}).status_code == 200
    r = client.patch("/api/inventory/properties/poe.budget", json={"type": "choice", "choices": ["370", "740"]})
    assert r.status_code == 200 and r.get_json()["choices"] == ["370", "740"]
    # Forgetting the type keeps the values people set with it.
    assert client.delete("/api/inventory/properties/poe.budget").status_code == 200
    assert "poe.budget" not in _catalog(client)
    assert client.get("/api/inventory/groups").get_json()["defaults"]["properties"] == {"poe.budget": "370"}
    assert client.delete("/api/inventory/properties/poe.budget").status_code == 404


def test_only_admins_define_properties(app_module, client):
    from tests.test_rbac import sign_in_as
    lead = sign_in_as(app_module, "le8", "lead")
    assert lead.get("/api/inventory/properties").status_code == 200
    assert lead.post("/api/inventory/properties", json={"key": "rack"}).status_code == 403


@pytest.mark.parametrize("kind,raw,out", [
    ("number", "1,5", "1.5"), ("number", "48", "48"), ("bool", "on", "true"), ("ip", "192.0.2.1", "192.0.2.1"),
    ("url", "https://example.com/api", "https://example.com/api"), ("text", "  a b ", "a b"), ("ip", "", ""),
])
def test_values_by_type(kind, raw, out):
    assert property_catalog.check({"type": kind, "label": "X", "choices": []}, raw) == out


@pytest.mark.parametrize("kind,raw", [("ip", "192.0.2.300"), ("url", "example.com"), ("bool", "maybe")])
def test_wrong_values_by_type(kind, raw):
    with pytest.raises(ScopeError):
        property_catalog.check({"type": kind, "label": "X", "choices": []}, raw)
