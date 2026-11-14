"""Tournament brackets (issue #107)."""
import pytest

from floorbit import brackets

TEAMS = ["Team Aurora", "Pixel Foxes", "Byte Club", "Lag Busters", "Null Pointers", "Ping Pirates"]


def names(rnd):
    return [(m["a"]["name"], m["b"]["name"]) for m in rnd]


def test_seeding_gives_byes_to_the_top_seeds():
    rounds = brackets.advance(brackets.seeded(TEAMS))
    assert [len(r) for r in rounds] == [4, 2, 1]
    assert names(rounds[0]) == [("Team Aurora", None), ("Lag Busters", "Null Pointers"),
                                ("Pixel Foxes", None), ("Byte Club", "Ping Pirates")]
    assert names(rounds[1]) == [("Team Aurora", None), ("Pixel Foxes", None)]   # byes moved up
    assert brackets.seeded(["a", "b"])[0][0]["id"] == "r1m1" and len(brackets.seeded(["a", "b"])) == 1


@pytest.fixture
def cup(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 40, "y": 50, "cols": 5, "rows": 2})
    zone = client.post("/api/tournament/zones", json={"name": "Main stage", "seats": "A"}).get_json()
    made = client.post("/api/tournament/brackets", json={"name": "Rocket Cup", "teams": "\n".join(TEAMS),
                                                         "zone_id": zone["id"]})
    assert made.status_code == 201
    return made.get_json()


def _match(client, bracket, match, **body):
    return client.patch(f"/api/tournament/brackets/{bracket['id']}/matches/{match}", json=body)


def test_results_move_winners_on_and_undo_cleanly(client, cup):
    assert _match(client, cup, "r1m2", a_score=1, b_score=2, winner="b").status_code == 200
    got = _match(client, cup, "r1m4", a_score=2, b_score=0, winner="a", seats="A-1..A-5", station="Stage").get_json()
    assert names(got["rounds"][1]) == [("Team Aurora", "Null Pointers"), ("Pixel Foxes", "Byte Club")]
    got = _match(client, cup, "r2m1", a_score=2, b_score=1, winner="a").get_json()
    assert got["rounds"][2][0]["a"]["name"] == "Team Aurora"
    # Changing the first-round result takes the wrong team out of the next rounds again.
    got = _match(client, cup, "r1m2", winner="a").get_json()
    assert got["rounds"][1][0]["b"]["name"] == "Lag Busters"
    assert got["rounds"][1][0]["winner"] is None and got["rounds"][1][0]["status"] == "waiting"
    view = client.get("/api/tournament/brackets").get_json()["brackets"][0]
    m4 = view["rounds"][0][3]
    assert m4["seats"] == ["A-1", "A-2", "A-3", "A-4", "A-5"]
    assert m4["zones"] == ["Main stage"] and m4["station"] == "Stage"


def test_bad_input_is_refused(client, cup):
    assert client.post("/api/tournament/brackets", json={"name": "x", "teams": "solo"}).status_code == 400
    assert client.post("/api/tournament/brackets", json={"name": "x", "teams": ["a", "A"]}).status_code == 400
    no_zone = {"name": "x", "teams": ["a", "b"], "zone_id": "nope"}
    assert client.post("/api/tournament/brackets", json=no_zone).status_code == 400
    assert _match(client, cup, "r1m2", a_score="lots").status_code == 400
    assert _match(client, cup, "r1m2", winner="c").status_code == 400
    assert _match(client, cup, "r3m1", winner="a").status_code == 400   # nobody there yet
    assert _match(client, cup, "r1m2", seats="Z-99").status_code == 400
    assert _match(client, cup, "r9m9", winner="a").status_code == 404


class _Registry:
    def __init__(self, result):
        self.result = result
        self.spec = type("Spec", (), {"name": "Toornament", "id": "toornament"})()

    def feeders(self, area):
        return [self.spec] if area == "brackets" else []

    def call(self, spec, method):
        return self.result


def test_plugin_brackets_are_imported_read_only(client, app_module, monkeypatch):
    first = [{"id": "x1", "name": "Open Cup", "rounds": [
        [{"a": {"name": "Red", "score": 2}, "b": {"name": "Blue", "score": 1}, "status": "done", "winner": "a"},
         {"a": {"name": "Green"}, "b": {"name": "Gold"}, "status": "live"}],
        [{"a": {"name": "Red"}, "b": {}}]]}, {"name": "broken"}]
    monkeypatch.setitem(app_module.app.extensions, "floorbit_plugins", _Registry(first))
    out = client.post("/api/tournament/brackets/import").get_json()
    assert out["count"] == 1 and out["errors"]
    b = client.get("/api/tournament/brackets").get_json()["brackets"][0]
    assert b["source"] == "import" and b["plugin"] == "Toornament" and b["rounds"][0][1]["status"] == "live"
    assert _match(client, b, "r1m2", winner="a").status_code == 409
    assert client.patch(f"/api/tournament/brackets/{b['id']}", json={"name": "Mine"}).status_code == 409
    # Importing again replaces it and keeps its id.
    first[0]["rounds"][0][1].update(status="done", winner="b")
    client.post("/api/tournament/brackets/import")
    again = client.get("/api/tournament/brackets").get_json()["brackets"]
    assert len(again) == 1 and again[0]["id"] == b["id"] and again[0]["rounds"][0][1]["winner"] == "b"


def test_viewers_cannot_change_brackets(app_module, cup):
    app_module.app.extensions["auth"].users.add("vic", "vic-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "vic", "password": "vic-password-1"})
    assert viewer.get("/api/tournament/brackets").status_code == 200
    assert _match(viewer, cup, "r1m2", winner="a").status_code == 403


def test_public_view_is_off_by_default_and_shows_no_seats(client, anon_client, cup):
    assert anon_client.get("/bracket").status_code == 404
    client.put("/api/settings", json={"public.brackets": True})
    _match(client, cup, "r1m2", a_score=0, b_score=2, winner="b", seats="A-1..A-5")
    _match(client, cup, "r1m4", status="live")
    body = anon_client.get("/bracket.json").get_json()["brackets"][0]
    assert body["zone"] == "Main stage" and body["live"] == 1
    assert [r["label"] for r in body["rounds"]] == ["quarter", "semi", "final"]
    assert "A-1" not in str(body) and "by" not in body
    page = anon_client.get(f"/bracket?id={cup['id']}").get_data(as_text=True)
    assert "Rocket Cup" in page and "Quarter-finals" in page and "Semi-finals" in page and "Live" in page
    assert "A-1" not in page
    de = anon_client.get("/bracket?screen=1", headers={"Accept-Language": "de-CH,de"}).get_data(as_text=True)
    assert "Halbfinals" in de and 'class="screen"' in de
