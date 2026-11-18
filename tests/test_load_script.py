"""scripts/load_test.py (issue #473) keeps working: a small hall."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


def test_the_load_test_runs_on_a_small_hall(monkeypatch, tmp_path):
    import load_test

    from floorbit import store
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    for name in ("CHECKIN_FILE", "FLOORBIT_DATABASE_URL", "CHECKIN_ALLOWED_NETWORKS"):
        monkeypatch.delenv(name, raising=False)
    results = load_test.main(["--seats", "60", "--ports", "24"])
    assert [label.split(":")[0] for label, _took, _per in results] == [
        "Unmatched clients", "Patch plan check", "Check-in", "Check-in history"]
