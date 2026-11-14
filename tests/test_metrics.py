"""Prometheus metrics (issue #153): aggregate counts only, off by default, readable with a token."""
import time

import pytest

from integrations import seat_sources


@pytest.fixture
def hall(client, app_module, monkeypatch):
    monkeypatch.setenv("SEAT_SOURCES", "manual")
    seat_sources.invalidate()
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 2})
    client.put("/api/seat-map/D-6", json={"ip": "198.51.100.7", "nick": "player-six"})
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    dev = {"id": "s1", "name": "sw-d-01"}
    stats.record([(dev, {"name": "Gi1/0/6", "state": "up", "download_bps": 5e6, "upload_bps": 1e6}, "D-6"),
                  (dev, {"name": "Gi1/0/7", "state": "down"}, "D-7")], ["sw-d-01"], now=time.time())
    watch = app_module.app.extensions["floorbit_attention"]
    monkeypatch.setattr(watch, "port_seats", {("sw-d-01", "Gi1/0/7"): "D-7"}, raising=False)


def test_off_by_default(client):
    assert client.get("/api/metrics").status_code == 404


def test_counts_without_people(client, hall):
    assert client.put("/api/settings", json={"metrics.enabled": True}).status_code == 200
    client.post("/api/incidents", json={"title": "No link", "seat": "D-7"})
    resp = client.get("/api/metrics")
    assert resp.status_code == 200 and resp.mimetype == "text/plain"
    text = resp.get_data(as_text=True)
    assert 'floorbit_seats{hall="Hall",state="online"} 1' in text
    assert 'floorbit_seats{hall="Hall",state="offline"} 1' in text
    assert 'floorbit_seats{hall="Hall",state="unknown"} 6' in text
    assert 'floorbit_seats_with_problems{hall="Hall"} 1' in text
    assert 'floorbit_incidents{status="open"} 1' in text
    assert "# TYPE floorbit_seats gauge" in text and "floorbit_port_read_age_seconds" in text
    for private in ("D-6", "D-7", "198.51.100.7", "player-six", "sw-d-01"):
        assert private not in text


def test_a_read_only_token_can_scrape(client, anon_client, app_module, hall, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    client.put("/api/settings", json={"metrics.enabled": True})
    made = client.post("/api/settings/api-tokens", json={"name": "grafana", "role": "viewer", "read_only": True})
    token = made.get_json()["secret"]
    assert anon_client.get("/api/metrics").status_code in (401, 302)
    resp = anon_client.get("/api/metrics", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200 and "floorbit_info" in resp.get_data(as_text=True)
