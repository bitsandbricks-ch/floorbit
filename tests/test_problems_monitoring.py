from floorbit import sources


def _down(monkeypatch, last_ok):
    monkeypatch.setattr(sources, "_health", {"source": "agent", "label": "Local agent", "ok": False,
                                             "offline_since": 1.0, "last_ok": last_ok, "error": "x"})


def _item(client, lang="en"):
    body = client.get("/api/problems", headers={"Accept-Language": lang}).get_json()
    return next(p for p in body["problems"] if p["kind"] == "monitoring")


def test_a_source_that_never_answered_reads_as_setup_to_do(client, monkeypatch):
    _down(monkeypatch, None)
    item = _item(client)
    assert item["title"] == "Local agent has not answered yet"
    assert item["link"] == "/settings/agents"
    assert _item(client, "de-CH")["title"] == "Der lokale Agent hat noch nicht geantwortet"


def test_a_source_that_stopped_answering_is_named_by_its_label(client, monkeypatch):
    _down(monkeypatch, 0.5)
    item = _item(client)
    assert item["title"] == "Local agent is not answering"
    assert item["where"] == "Switch status is frozen at the last good data"
