"""The page list behind "Go to" on every page (issue #250)."""
from tests.test_rbac import sign_in_as


def hrefs(client):
    answer = client.get("/api/pages")
    assert answer.status_code == 200
    return [p["href"] for p in answer.get_json()["pages"]]


def test_everything_while_sign_in_is_off(client):
    pages = client.get("/api/pages").get_json()["pages"]
    assert pages[:2] == [{"href": "/overview", "id": "overview", "label": "Overview"},
                         {"href": "/plan", "id": "floorPlan", "label": "Floor plan"}]
    got = [p["href"] for p in pages]
    assert "/settings" in got and "/terminal" in got


def test_features_that_are_off_are_left_out(client):
    client.put("/api/settings/features", json={"dashboard": False})
    assert "/dashboard" not in hrefs(client)


def test_a_role_only_sees_its_pages(app_module):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    got = hrefs(viewer)
    assert "/problems" in got
    assert not {"/settings", "/settings/users", "/jobs", "/terminal", "/timeline"} & set(got)
    admin = sign_in_as(app_module, "ad1", "admin")
    assert {"/settings", "/settings/users", "/timeline"} <= set(hrefs(admin))


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


def test_monitoring_pages_have_their_own_address(client, built):
    # Each Monitoring view is a page too (Network > Wi-Fi, Services > DNS, Traffic, ...). Service
    # health is part of Services now (issue #1337).
    for path in ("/services", "/dns", "/traffic", "/games", "/stats", "/speedtests"):
        assert client.get(path).status_code == 200, path
    assert client.get("/health").status_code == 404
    got = hrefs(client)
    assert {"/services", "/dns", "/traffic", "/games", "/stats", "/speedtests"} <= set(got) and "/health" not in got
    # No Wi-Fi source and no LAN cache plugin: their pages stay out of the list.
    assert "/wifi" not in got and "/lancache" not in got


def test_a_monitoring_page_goes_with_its_feature(client):
    client.put("/api/settings/features", json={"traffic": False})
    got = hrefs(client)
    assert "/traffic" not in got
    assert client.get("/traffic").status_code == 404
