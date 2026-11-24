"""A plan pane shows its area, one saved view, a tour through stops, or the hall beside a spotlight."""
import pytest

PANE = {"kind": "plan", "hall": "", "area": {"kind": "hall"}, "preset": "overview", "show": "all", "labels": "auto"}
VIEW = {"name": "VIP corner", "hall": "main", "view": {"x": 10, "y": 20, "w": 300, "h": 200}, "show": "problems"}


def _put(client, public=False, **over):
    return client.put("/api/dashboards/wall", json={"name": "Wall", "public": public,
                                                     "root": {"pane": {**PANE, **over}}})


def _pane(response):
    return response.get_json()["sections"][0]["panels"][0]["node"]["pane"]


def test_area_leaves_no_fields(client):
    pane = _pane(_put(client))
    assert not {"shows", "view", "stops", "secs", "on_problem"} & set(pane)


def test_one_view_and_tour_are_kept(client):
    assert _pane(_put(client, shows="view", view="abc123"))["view"] == "abc123"
    pane = _pane(_put(client, shows="tour", stops={"whole": False, "views": ["a1", "a1", "b2"]}, secs=8))
    assert pane["stops"] == {"whole": False, "blocks": True, "views": ["a1", "b2"]}
    assert pane["secs"] == 8 and pane["on_problem"] == "next"
    assert _pane(_put(client, shows="spotlight", on_problem="keep"))["on_problem"] == "keep"


@pytest.mark.parametrize("over", [
    {"shows": "slideshow"},
    {"shows": "view"},
    {"shows": "view", "view": "Not An Id!"},
    {"shows": "tour", "stops": {"whole": False, "blocks": False}},
    {"shows": "tour", "stops": {"views": ["x"] * 21 + [str(n) for n in range(21)]}},
    {"shows": "tour", "secs": 2},
    {"shows": "tour", "secs": True},
    {"shows": "tour", "on_problem": "panic"},
])
def test_checks(client, over):
    assert _put(client, **over).status_code == 400


def test_public_screen_gets_only_shared_views(client, anon_client):
    shared = client.post("/api/plan-views", json=VIEW).get_json()
    mine = client.post("/api/plan-views", json={**VIEW, "name": "Mine", "private": True}).get_json()
    assert _put(client, public=True, shows="tour", stops={"views": [shared["id"], mine["id"]]}).status_code == 200

    board = anon_client.get("/api/dashboards/wall/public").get_json()["board"]
    pane = board["sections"][0]["panels"][0]["node"]["pane"]
    assert pane["views"] == [{"id": shared["id"], "name": "VIP corner", "hall": "main",
                              "view": {"x": 10.0, "y": 20.0, "w": 300.0, "h": 200.0}, "show": "problems"}]
