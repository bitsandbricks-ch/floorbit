"""One count of the services (issue #1037): the health wall's checks, each internet site a row."""
from floorbit import service_summary


def test_sites_are_rows_and_counts_add_up():
    checks = [
        {"id": "dhcp-players", "name": "DHCP players", "kind": "dhcp", "status": "warn", "summary": "24 left", "link": ""},
        {"id": "firewall:1", "name": "fw-03", "kind": "firewall", "status": "down", "summary": "", "link": "/firewalls"},
        {"id": "sites", "name": "Internet sites", "kind": "web", "status": "up", "summary": "", "link": "/services"},
        {"id": "odd", "name": "Odd", "kind": "other", "status": "weird", "summary": "", "link": ""},
    ]
    sites = [{"id": "g", "name": "Google", "status": "up"}, {"id": "s", "name": "Steam", "status": "down", "error": "timeout"}]
    out = service_summary.summary(checks, sites)
    assert [r["name"] for r in out["rows"]] == ["DHCP players", "fw-03", "Google", "Steam", "Odd"]
    assert out["total"] == 5
    assert out["counts"] == {"up": 1, "warn": 1, "down": 2, "unknown": 1}
    assert out["by_kind"]["web"] == {"up": 1, "warn": 0, "down": 1, "unknown": 0, "total": 2}
    # Without the sites, the wall's one tile stays.
    assert service_summary.summary(checks)["total"] == 4


def test_the_endpoint_counts_what_the_wall_counts(client, app_module, monkeypatch):
    wall = app_module.app.extensions["floorbit_health"]
    monkeypatch.setattr(wall, "fresh", lambda: {"checks": [
        {"id": "firewall:1", "name": "fw-03", "kind": "firewall", "status": "down", "summary": "1 range failed over", "link": "/firewalls"}]})
    out = client.get("/api/services/summary").get_json()
    assert out["total"] == 1 and out["counts"]["down"] == 1 and out["rows"][0]["kind"] == "firewall"
