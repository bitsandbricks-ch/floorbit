"""The public attendee view (issue #19): seats online or offline, nothing else."""
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
    stats.record([(dev, {"name": "Gi1/0/6", "state": "up", "download_bps": 5e6, "upload_bps": 1e6,
                         "mac": "02:00:00:00:00:06"}, "D-6"),
                  (dev, {"name": "Gi1/0/7", "state": "down"}, "D-7")], ["sw-d-01"], now=time.time())
    return stats


@pytest.fixture
def switched_on(client):
    assert client.put("/api/settings", json={"public.attendee_view": True}).status_code == 200


def test_off_by_default(anon_client, hall):
    assert anon_client.get("/hall").status_code == 404
    assert anon_client.get("/api/public/seats").status_code == 404
    assert anon_client.get("/api/public/hall").status_code == 404


def test_seats_online_without_an_account(anon_client, hall, switched_on, app_module, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    data = anon_client.get("/api/public/seats").get_json()
    assert data["seats"]["D-6"] is True and data["seats"]["D-7"] is False
    assert data["online"] == 1 and data["total"] == 8 and len(data["seats"]) == 8
    # What the React page (PublicHall.tsx) draws.
    assert anon_client.get("/hall").status_code in (200, 503)
    hall = anon_client.get("/api/public/hall").get_json()
    assert hall["online"] == 1 and hall["total"] == 8 and hall["halls"] == []
    cells = [c for b in hall["drawing"]["shapes"] for c in b["cells"]]
    assert [c["seat"] for c in cells if c["on"]] == ["D-6"]


def test_nothing_personal(anon_client, hall, switched_on):
    for path in ("/hall", "/api/public/hall", "/api/public/seats"):
        body = anon_client.get(path).get_data(as_text=True)
        for secret in ("player-six", "198.51.100.7", "02:00:00:00:00:06", "sw-d-01", "Gi1/0/6"):
            assert secret not in body, (path, secret)


def test_old_reads_are_unknown(anon_client, hall, switched_on):
    hall.last = time.time() - 3600
    data = anon_client.get("/api/public/seats").get_json()
    assert data["online"] is None and set(data["seats"].values()) == {None}
    hall_view = anon_client.get("/api/public/hall").get_json()
    assert hall_view["online"] is None
    assert {c["on"] for b in hall_view["drawing"]["shapes"] for c in b["cells"]} == {None}


def test_empty_hall(anon_client, switched_on):
    body = anon_client.get("/api/public/hall").get_json()
    assert body["drawing"] is None and body["total"] == 0


def test_more_halls_to_switch_to(client, anon_client, hall, switched_on):
    side = client.post("/api/halls", json={"name": "Side hall"}).get_json()["id"]
    body = anon_client.get("/api/public/hall", query_string={"hall": side}).get_json()
    assert body["hall"] == side and [h["name"] for h in body["halls"]][-1] == "Side hall"
    assert body["drawing"] is None   # no blocks there yet


def test_switch_needs_settings_manage(anon_client, hall):
    assert anon_client.put("/api/settings", json={"public.attendee_view": True}).status_code in (401, 403)
