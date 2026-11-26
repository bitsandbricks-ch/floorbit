"""A new block's spacer between its rows (#1547)."""
import pytest


def _make(client, **fields):
    return client.post("/api/seat-blocks", json={"x": 40, "y": 40, "cols": 8, **fields})


def test_a_new_run_of_two_rows_gets_the_spacer_between_them(client):
    res = _make(client, rows=2, spacer=1)
    assert res.status_code == 201, res.get_json()
    assert [r["gap"] for r in res.get_json()["rows"]] == [0, 1]


def test_no_spacer_keeps_the_rows_touching(client):
    assert [r["gap"] for r in _make(client, rows=3).get_json()["rows"]] == [0, 0, 0]


@pytest.mark.parametrize("spacer", [-1, 21, "nan"])
def test_the_spacer_must_fit(client, spacer):
    assert _make(client, rows=2, spacer=spacer).status_code == 400


def test_add_several_runs_carries_the_spacer(client):
    res = client.post("/api/seat-blocks/many", json={"x": 20, "y": 20, "cols": 8, "rows": 2, "spacer": 0.5,
                                                    "count": 3, "dy": 15, "naming": "rows", "row_start": "A"})
    assert res.status_code == 201, res.get_json()
    assert all([r["gap"] for r in b["rows"]] == [0, 0.5] for b in res.get_json())
