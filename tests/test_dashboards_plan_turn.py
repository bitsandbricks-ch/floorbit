"""A plan pane can turn a tall hall to fill a wide box (``turn``); it is kept only when on."""


def _save(client, **over):
    pane = {"kind": "plan", "hall": "", "area": {"kind": "hall"}, "preset": "overview", "show": "all", "labels": "auto"}
    saved = client.put("/api/dashboards/wall", json={"name": "Wall", "root": {"pane": {**pane, **over}}}).get_json()
    return saved["sections"][0]["panels"][0]["node"]["pane"]


def test_turn_is_kept_when_on(client):
    assert _save(client, turn=True)["turn"] is True


def test_turn_off_leaves_no_field(client):
    assert "turn" not in _save(client, turn=False)
