"""More than one hall, background images and the CSV import of seat blocks (issue #20)."""
import base64

import pytest

from floorbit import store

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
CSV = "name,x,y,cols,rows,rotation\nE,20,30,6,2,0\nF;bad\n"


@pytest.fixture
def two_halls(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 2, "rows": 1})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 5, "y": 5}).get_json()
    hall2 = client.post("/api/halls", json={"name": "Hall 2"}).get_json()
    return {"switch": sw, "hall2": hall2}


def test_an_old_install_is_one_hall(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 2, "rows": 1})
    halls = client.get("/api/halls").get_json()["halls"]
    assert halls == [{"id": "main", "name": "Hall", "background": None, "background_frame": None,
                      "background_opacity": None,
                      "seat_m": None, "switches": 0, "seat_blocks": 1}]
    assert client.get("/api/seat-blocks").get_json()[0]["hall_id"] == "main"


def test_items_go_in_their_hall(client, two_halls):
    h2 = two_halls["hall2"]["id"]
    block = client.post("/api/seat-blocks", json={"name": "B", "x": 50, "y": 50, "hall_id": h2}).get_json()
    assert block["hall_id"] == h2
    assert [b["name"] for b in client.get(f"/api/seat-blocks?hall={h2}").get_json()] == ["B"]
    assert [b["name"] for b in client.get("/api/seat-blocks?hall=main").get_json()] == ["A"]
    # Moving the switch to hall 2, and the hall list counts follow.
    sw = client.put(f"/api/switches/{two_halls['switch']['id']}", json={"x": 1, "y": 2, "hall_id": h2}).get_json()
    assert sw["hall_id"] == h2
    counts = {h["name"]: (h["switches"], h["seat_blocks"]) for h in client.get("/api/halls").get_json()["halls"]}
    assert counts == {"Hall": (0, 1), "Hall 2": (1, 1)}
    assert [s["name"] for s in client.get("/api/switches?hall=main").get_json()] == []


def test_unknown_hall_is_refused(client, two_halls):
    assert client.post("/api/seat-blocks", json={"x": 1, "y": 1, "hall_id": "nope"}).status_code == 400
    assert client.post("/api/switches", json={"x": 1, "y": 1, "hall_id": "nope"}).status_code == 400


def test_rename_and_delete(client, two_halls):
    h2 = two_halls["hall2"]["id"]
    assert client.put(f"/api/halls/{h2}", json={"name": "  Upper  floor "}).get_json()["name"] == "Upper floor"
    assert client.put(f"/api/halls/{h2}", json={"name": " "}).status_code == 400
    # A hall with something in it stays; an empty one goes; the last one always stays.
    assert client.delete("/api/halls/main").status_code == 409
    assert client.delete(f"/api/halls/{h2}").status_code == 200
    blocks = client.get("/api/seat-blocks").get_json()
    client.delete(f"/api/seat-blocks/{blocks[0]['id']}")
    client.delete(f"/api/switches/{two_halls['switch']['id']}")
    assert client.delete("/api/halls/main").status_code == 409


def test_background_image(client, two_halls, anon_client, app_module, monkeypatch):
    h2 = two_halls["hall2"]["id"]
    hall = client.put(f"/api/halls/{h2}/background", json={"image": PNG}).get_json()
    assert hall["background"].startswith(f"/api/halls/{h2}/background?v=")
    resp = client.get(hall["background"])
    assert resp.status_code == 200 and resp.mimetype == "image/png"
    assert "sandbox" in resp.headers["Content-Security-Policy"]
    assert resp.data.startswith(b"\x89PNG")
    bad = client.put(f"/api/halls/{h2}/background", json={"image": "data:text/html;base64,PHA+"})
    assert bad.status_code == 400
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    assert anon_client.get(hall["background"]).status_code in (302, 401)
    assert client.delete(f"/api/halls/{h2}/background").get_json()["background"] is None
    assert client.get(f"/api/halls/{h2}/background").status_code == 404


def test_csv_import_is_all_or_nothing(client, two_halls):
    h2 = two_halls["hall2"]["id"]
    resp = client.post(f"/api/halls/{h2}/seat-blocks.csv", json={"csv": CSV})
    assert resp.status_code == 400 and resp.get_json()["errors"][0]["line"] == 3
    assert client.get(f"/api/seat-blocks?hall={h2}").get_json() == []
    resp = client.post(f"/api/halls/{h2}/seat-blocks.csv", data="name;x;y;cols;rows\nE;20;30;6;2\nG;60,5;30;4;1\n",
                       content_type="text/csv")
    assert resp.status_code == 201 and resp.get_json()["added"] == 2
    blocks = client.get(f"/api/seat-blocks?hall={h2}").get_json()
    assert [(b["name"], b["x"], b["cols"]) for b in blocks] == [("E", 20.0, 6), ("G", 60.5, 4)]
    # Block names make seat numbers, so they stay unique across halls.
    again = client.post("/api/halls/main/seat-blocks.csv", json={"csv": "name,x,y,cols,rows\nE,1,1,1,1\n"})
    assert again.status_code == 400 and "already" in again.get_json()["errors"][0]["error"]
    assert client.post("/api/halls/main/seat-blocks.csv", json={"csv": "a,b\n1,2\n"}).status_code == 400


def test_a_seat_block_file_csv_cannot_read_is_refused_not_a_crash(client, two_halls):
    h2 = two_halls["hall2"]["id"]
    long_field = "name,x,y,cols,rows,rotation\nE,20,30,6,2," + "9" * 200_000 + "\n"
    resp = client.post(f"/api/halls/{h2}/seat-blocks.csv", json={"csv": long_field})
    assert resp.status_code == 400
    assert resp.get_json()["errors"] == [{"line": 2, "error": "Line 2 cannot be read as CSV."}]
    twice = client.post(f"/api/halls/{h2}/seat-blocks.csv", json={"csv": "name,x,y,cols,rows,x\nE,20,30,6,2,90\n"})
    assert twice.status_code == 400 and "twice: x" in twice.get_json()["errors"][0]["error"]


def test_backup_carries_every_hall(client, two_halls):
    h2 = two_halls["hall2"]["id"]
    client.put(f"/api/halls/{h2}/background", json={"image": PNG})
    client.post("/api/seat-blocks", json={"name": "B", "x": 50, "y": 50, "hall_id": h2})
    backup = client.get("/api/settings/backup").get_json()
    assert [h["name"] for h in backup["layout"]["halls"]] == ["Hall", "Hall 2"]
    assert backup["layout"]["halls"][1]["background"] == PNG
    # Wipe the halls, then restore.
    client.delete(f"/api/halls/{h2}/background")
    data = store.load_data()
    data["halls"] = []
    store.save_data(data)
    result = client.post("/api/settings/backup", json=backup).get_json()
    assert result["restored"]["halls"] == 2
    halls = client.get("/api/halls").get_json()["halls"]
    assert halls[1]["id"] == h2 and halls[1]["background"] and halls[1]["seat_blocks"] == 1
    assert client.get(halls[1]["background"]).data.startswith(b"\x89PNG")


def test_backup_with_a_bad_hall_is_refused(client):
    backup = client.get("/api/settings/backup").get_json()
    backup["layout"]["halls"] = [{"id": "x y", "name": "Bad"}]
    assert client.post("/api/settings/backup", json=backup).status_code == 400
    backup["layout"]["halls"] = [{"id": "h", "name": "Bad", "background": "data:image/gif;base64,R0lG"}]
    assert client.post("/api/settings/backup", json=backup).status_code == 400


def test_seat_finder_names_the_hall(client, anon_client, two_halls):
    h2 = two_halls["hall2"]["id"]
    client.post("/api/seat-blocks", json={"name": "B", "x": 50, "y": 50, "cols": 2, "rows": 1, "hall_id": h2})
    body = anon_client.get("/api/seat-finder?q=B-1").get_json()
    assert body["found"]["seat"] == "B-1" and body["found"]["hall"] == "Hall 2"
    assert [c["seat"] for b in body["drawing"]["shapes"] for c in b["cells"]] == ["B-1", "B-2"]   # only hall 2


def test_screen_passes_the_hall_on(client, two_halls):
    h2 = two_halls["hall2"]["id"]
    views = client.get(f"/api/screen?views=floor,stats&hall={h2}").get_json()["views"]
    assert [v["url"] for v in views] == [f"/dashboards/kiosk?hall={h2}", "/stats?screen=1"]
    assert "hall=" not in str(client.get("/api/screen?hall=../x").get_json()["views"])


PNG = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAA'
       'SUVORK5CYII=')


def test_a_background_moves_scales_and_fades_and_a_hall_gets_its_scale(client):
    # Mike: a drawing under the plan, calibrated to the seats.
    assert client.put('/api/halls/main/background', json={'image': PNG}).status_code == 200
    placed = {'frame': {'x': -5, 'y': 10, 'w': 120, 'h': 80}, 'opacity': 0.4}
    body = client.patch('/api/halls/main/background', json=placed).get_json()
    assert body['background_frame'] == {'x': -5, 'y': 10, 'w': 120, 'h': 80} and body['background_opacity'] == 0.4
    plan = client.get('/api/plan?hall=main').get_json()
    assert plan['background_frame'] == {'x': -80, 'y': 100, 'w': 1920, 'h': 800} and plan['background_opacity'] == 0.4
    for bad in ({'opacity': 0}, {'opacity': 'x'}, {'frame': {'x': 0, 'y': 0, 'w': 0, 'h': 5}}, {'frame': [1, 2]}):
        assert client.patch('/api/halls/main/background', json=bad).status_code == 400, bad
    assert client.put('/api/halls/main/scale', json={'seat_m': 0.8}).get_json()['seat_m'] == 0.8
    assert client.put('/api/halls/main/scale', json={'seat_m': 50}).status_code == 400
    assert client.put('/api/halls/main/scale', json={'seat_m': None}).get_json()['seat_m'] is None
    # A new image starts on the whole plan again.
    again = client.put('/api/halls/main/background', json={'image': PNG}).get_json()
    assert again['background_frame'] == {'x': 0, 'y': 0, 'w': 100, 'h': 100}
    client.delete('/api/halls/main/background')
    assert client.patch('/api/halls/main/background', json={'opacity': 0.5}).status_code == 400
