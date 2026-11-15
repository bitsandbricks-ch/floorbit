"""The page list behind "Go to" on every page (issue #250)."""
import re

from tests.test_rbac import sign_in_as


def hrefs(client):
    answer = client.get("/api/pages")
    assert answer.status_code == 200
    return [p["href"] for p in answer.get_json()["pages"]]


def test_everything_while_sign_in_is_off(client):
    pages = client.get("/api/pages").get_json()["pages"]
    assert pages[0] == {"href": "/", "id": "floorPlan", "label": "Floor plan"}
    got = [p["href"] for p in pages]
    assert "/settings" in got and "/terminal" in got


def test_features_that_are_off_are_left_out(client):
    client.put("/api/settings/features", json={"dashboard": False})
    assert "/dashboard" not in hrefs(client)


def test_a_role_only_sees_its_pages(app_module):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    got = hrefs(viewer)
    assert "/problems" in got
    assert not {"/settings", "/settings/users", "/jobs", "/terminal", "/planner"} & set(got)
    admin = sign_in_as(app_module, "ad1", "admin")
    assert {"/settings", "/settings/users", "/planner"} <= set(hrefs(admin))


def test_the_list_agrees_with_the_floor_plan_top_bar(app_module):
    # Same conditions as the top bar, so "Go to" never offers a page the top bar hides or misses one.
    for who, role in (("ad1", "admin"), ("vi1", "viewer"), ("te1", "tech")):
        crew = sign_in_as(app_module, who, role)
        top_bar = re.search(r'<nav class="topbar-nav".*?</nav>', crew.get("/").get_data(as_text=True), re.S).group(0)
        linked = set(re.findall(r'href="(/[^"#?]*)"', top_bar))
        listed = set(hrefs(crew))
        assert linked <= listed, (role, linked - listed)
        for href in ("/wifi", "/power", "/commands", "/logs", "/security", "/incidents", "/seat-mapping"):
            assert (href in linked) == (href in listed), (role, href)


def test_the_server_pages_have_the_go_to_button(client):
    for path in ("/", "/settings", "/settings/audit", "/settings/users"):
        html = client.get(path).get_data(as_text=True)
        assert "data-goto=" in html and "/static/js/goto.js" in html and "/static/css/goto.css" in html, path


def test_go_to_finds_seats_and_switches(client):
    from floorbit import store
    data = store.load_data()
    data["seat_blocks"] = [{"id": "b1", "name": "B", "cols": 4, "rows": 2}]
    data["inventory"] = [{"id": "s1", "name": "sw-b-01"}]
    store.save_data(data)
    seat, name = "B-8", "sw-b-01"
    found = client.get("/api/pages/find", query_string={"q": seat.replace("-", "").lower()}).get_json()["places"]
    assert found[0] == {"kind": "seat", "name": seat, "href": f"/plan?seat={seat}"}
    found = client.get("/api/pages/find", query_string={"q": "sw-b"}).get_json()["places"]
    assert {"kind": "switch", "name": name, "href": f"/plan?switch={name}"} in found
    # One letter finds nothing: too many seats start with it.
    assert client.get("/api/pages/find?q=b").get_json() == {"places": []}
    assert client.get("/api/pages/find").get_json() == {"places": []}


def test_places_order_and_limit():
    from floorbit import page_index
    data = {"seat_blocks": [{"name": "B", "cols": 12, "rows": 1}],
            "inventory": [{"id": "1", "name": "sw-b-01"}, {"id": "2", "name": "core-b"}]}
    found = page_index.places("b1", data)
    # Exact seat first, then the ones it starts, in seat order; at most five.
    assert [p["name"] for p in found if p["kind"] == "seat"] == ["B-1", "B-10", "B-11", "B-12"]
    assert [p["name"] for p in page_index.places("b", data)] == []
    # Switches: names that start with it before names that only contain it.
    assert [p["name"] for p in page_index.places("swb", data)] == ["sw-b-01"]
    assert [p["name"] for p in page_index.places("b0", data) if p["kind"] == "switch"] == ["sw-b-01"]


def test_a_viewer_finds_places_without_people(app_module):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    answer = viewer.get("/api/pages/find?q=sw")
    assert answer.status_code == 200
    assert all(set(p) == {"kind", "name", "href"} for p in answer.get_json()["places"])
