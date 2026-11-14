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
    assert halls == [{"id": "main", "name": "Hall", "background": None, "switches": 0, "seat_blocks": 1}]
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
    page = anon_client.get("/find?q=B-1").get_data(as_text=True)
    assert "Seat B-1" in page and "<strong>Hall 2</strong>" in page
    assert page.count('class="cell') == 2   # only hall 2 is drawn


def test_attendee_view_per_hall(client, anon_client, two_halls):
    h2 = two_halls["hall2"]["id"]
    client.put("/api/settings", json={"public.attendee_view": True})
    client.post("/api/seat-blocks", json={"name": "B", "x": 50, "y": 50, "cols": 3, "rows": 1, "hall_id": h2})
    page = anon_client.get(f"/hall?hall={h2}").get_data(as_text=True)
    assert 'aria-current="page">Hall 2' in page and page.count('data-seat="B-') == 3 and 'data-seat="A-' not in page
    assert anon_client.get(f"/api/public/seats?hall={h2}").get_json()["total"] == 3
    assert anon_client.get("/api/public/seats").get_json()["total"] == 5


def test_screen_passes_the_hall_on(client, two_halls):
    h2 = two_halls["hall2"]["id"]
    page = client.get(f"/screen?views=floor,stats&hall={h2}").get_data(as_text=True)
    assert f'data-src="/kiosk?hall={h2}"' in page and 'data-src="/stats?screen=1"' in page
    assert "hall=" not in client.get("/screen?hall=../x").get_data(as_text=True)
