"""Rough port areas (floorbit/port_areas.py): batches of ports to a range of seats. Made-up
switches and nicks, RFC 5737 addresses."""
import pytest

from floorbit import port_areas
from floorbit.store import load_data
from integrations import checkin, events


@pytest.fixture
def row(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKIN_ENABLED", "true")
    monkeypatch.setenv("CHECKIN_FILE", str(tmp_path / "checkins.json"))
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: None)
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 20, "rows": 2})
    return client


def batch(client, **body):
    return client.post("/api/port-areas/batch", json={"switch": "sw-a-01", "size": 10, **body})


def test_quick_entry_makes_one_area_per_batch_and_skips_empty_ones(row):
    r = batch(row, starts=["A-1", "A-11", "", "A-21"])
    assert r.status_code == 200, r.get_json()
    areas = row.get("/api/port-areas").get_json()["areas"]
    assert [(a["first"], a["last"], a["label"]) for a in areas] == [
        (1, 10, "A-1..A-10"), (11, 20, "A-11..A-20"), (31, 40, "A-21..A-30")]
    # A second entry for the same switch replaces the first, so a fix is one more entry.
    batch(row, starts=["A-31"])
    assert [a["label"] for a in row.get("/api/port-areas").get_json()["areas"]] == ["A-31..A-40"]


def test_quick_entry_refuses_typos_and_previews(row):
    assert batch(row, starts=["Z-1"]).status_code == 400
    assert "A-41" in batch(row, starts=["A-35"]).get_json()["error"]          # runs past the block
    assert batch(row, starts=["", ""]).status_code == 400
    r = batch(row, starts=["A-1"], dry_run=True)
    assert r.get_json()["areas"][0]["seats"][-1] == "A-10" and port_areas.all_areas() == []
    de = row.post("/api/port-areas/batch", json={"switch": "sw-a-01", "starts": ["Z-1"]},
                  headers={"Accept-Language": "de-CH"})
    assert "Platznummer" in de.get_json()["error"] or "nicht im Plan" in de.get_json()["error"]


def test_a_port_names_its_area(row):
    batch(row, starts=["A-1", "A-11"])
    assert port_areas.hint("sw-a-01", "Gi1/0/14")["label"] == "A-11..A-20"
    assert port_areas.hint("SW-A-01.example.com", "GigabitEthernet1/0/3")["label"] == "A-1..A-10"
    assert port_areas.hint("sw-a-01", "Gi1/0/48") is None
    r = row.get("/api/port-areas/lookup?switch=sw-a-01&port=Gi1/0/2").get_json()
    assert r["area"]["seats"][0] == "A-1"


def test_a_check_in_far_from_its_area_goes_to_review(row):
    batch(row, starts=["A-1", "A-11"])
    checkin.learn_port("A-15", {"switch": "sw-a-01", "port": "Gi1/0/3"}, "pixel")   # port of A-1..A-10
    checkin.learn_port("A-12", {"switch": "sw-a-01", "port": "Gi1/0/12"}, "nova")   # where it belongs
    conflicts = checkin.port_conflicts(load_data())
    assert [(c["kind"], c["seat"], c["other"]) for c in conflicts] == [("area", "A-15", ["A-1..A-10"])]


def test_deleting_areas(row):
    made = batch(row, starts=["A-1", "A-11"]).get_json()["areas"]
    assert row.delete(f"/api/port-areas/{made[0]['id']}").status_code == 200
    assert row.delete(f"/api/port-areas/{made[0]['id']}").status_code == 404
    assert row.delete("/api/port-areas?switch=SW-A-01").get_json() == {"deleted": 1}
