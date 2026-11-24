"""Blocks named by their rows have no name of their own: each keeps its own summary and panel (issue #1030)."""


def test_blocks_named_by_rows_keep_their_own_summary_and_panel(client):
    for x, start in ((30, "C"), (60, "E")):
        res = client.post("/api/seat-blocks", json={"cols": 4, "rows": 2, "x": x, "y": 40, "naming": "rows",
                                                    "row_start": start})
        assert res.status_code == 201, res.get_json()
    blocks = client.get("/api/plan").get_json()["blocks"]
    dash = chr(0x2013)   # the label's en dash
    assert sorted(b["label"] for b in blocks) == [f"C{dash}D", f"E{dash}F"]
    assert len({b["id"] for b in blocks}) == 2
    for b in blocks:
        panel = client.get(f"/api/plan/blocks/{b['id']}").get_json()
        assert panel["id"] == b["id"] and panel["label"] == b["label"] and panel["seats"] == 8
