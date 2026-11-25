"""One disk budget for all an agent keeps on disk (#1485)."""
import os

import pytest

from floorbit import disk_budget
from floorbit.flows import store
from tests.test_flows import NOW

MB = 1024 * 1024


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    monkeypatch.setattr(disk_budget, "_kinds", {})
    monkeypatch.setattr(disk_budget, "_dropped", {})
    monkeypatch.setattr(disk_budget, "_last", {})


def fill(folder, names, size, start):
    os.makedirs(folder, exist_ok=True)
    for i, name in enumerate(names):
        path = os.path.join(folder, name)
        with open(path, "wb") as f:
            f.write(b"x" * size)
        os.utime(path, (start + i * 3600, start + i * 3600))


def test_past_the_budget_the_oldest_files_go_whatever_kind(tmp_path, monkeypatch):
    monkeypatch.setenv(disk_budget.ENV, "3")
    raw = store.RawStore(str(tmp_path / "flows"))                        # registers "flows"
    fill(raw.raw, [f"2027-01-0{d}-00.jsonl.gz" for d in (1, 3, 5)], MB, NOW)  # at hours 0, 1, 2
    disk_budget.register("buffer", disk_budget.Folder(str(tmp_path / "outbox"), "*.jsonl"))
    fill(str(tmp_path / "outbox"), ["000000000001.jsonl", "000000000002.jsonl"], MB, NOW + 1800)  # 0.5, 1.5
    rep = disk_budget.enforce(now=NOW + 5 * 3600)
    assert rep["budget"] == 3 * MB and not rep["auto"] and rep["used"] <= 3 * MB
    # 5 MB in, 3 MB allowed: the two oldest go, hour 0 (flows) and hour 0.5 (buffer).
    assert sorted(os.listdir(raw.raw)) == ["2027-01-03-00.jsonl.gz", "2027-01-05-00.jsonl.gz"]
    assert os.listdir(tmp_path / "outbox") == ["000000000002.jsonl"]
    assert rep["kinds"]["flows"] == {"bytes": 2 * MB, "files": 2, "hours": 4.0, "dropped": 1}
    assert rep["kinds"]["buffer"]["dropped"] == 1 and disk_budget.report() == rep


def test_the_newest_file_of_each_kind_always_stays(tmp_path, monkeypatch):
    monkeypatch.setenv(disk_budget.ENV, "1")
    disk_budget.register("a", disk_budget.Folder(str(tmp_path / "a")))
    disk_budget.register("b", disk_budget.Folder(str(tmp_path / "b")))
    fill(str(tmp_path / "a"), ["1", "2"], 2 * MB, NOW)
    fill(str(tmp_path / "b"), ["1"], 2 * MB, NOW - 3600)
    rep = disk_budget.enforce(now=NOW + 3600)
    assert os.listdir(tmp_path / "a") == ["2"] and os.listdir(tmp_path / "b") == ["1"]
    assert rep["used"] == 4 * MB    # still over: the files being written stay


def test_a_new_budget_applies_on_the_next_pass(tmp_path, monkeypatch):
    disk_budget.register("a", disk_budget.Folder(str(tmp_path / "a")))
    fill(str(tmp_path / "a"), ["1", "2", "3"], MB, NOW)
    monkeypatch.setenv(disk_budget.ENV, "10")
    assert disk_budget.enforce(now=NOW)["kinds"]["a"]["files"] == 3
    monkeypatch.setenv(disk_budget.ENV, "1")
    assert disk_budget.enforce(now=NOW)["kinds"]["a"]["files"] == 1


def test_automatic_is_half_of_what_the_volume_could_hold(tmp_path, monkeypatch):
    monkeypatch.delenv(disk_budget.ENV, raising=False)
    disk_budget.register("a", disk_budget.Folder(str(tmp_path / "a")))
    fill(str(tmp_path / "a"), ["1"], MB, NOW)
    monkeypatch.setattr(disk_budget, "_free", lambda paths: 9 * MB)
    rep = disk_budget.enforce(now=NOW)
    assert rep["auto"] and rep["budget"] == 5 * MB


def test_the_hosted_side_keeps_only_numbers():
    raw = {"budget": 5, "used": 3, "auto": True, "evil": "<b>",
           "kinds": {"flows": {"bytes": 3, "hours": 2.5, "files": "x", "dropped": -1},
                     "x" * 99: {"bytes": 1}, "bad": "row"}}
    assert disk_budget.clean(raw) == {"auto": True, "budget": 5, "used": 3,
                                      "kinds": {"flows": {"bytes": 3, "hours": 2.5}}}
    assert disk_budget.clean("nope") is None and disk_budget.clean({"kinds": []}) is None
