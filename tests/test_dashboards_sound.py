"""A dashboard's sound for new problems (#1137): off unless asked for, kept on save."""


def test_sound_is_off_unless_the_dashboard_asks_for_it(client):
    body = {"name": "NOC", "fit": True, "sections": [{"panels": []}]}
    assert "sound" not in client.put("/api/dashboards/noc", json=body).get_json()
    saved = client.put("/api/dashboards/noc", json={**body, "sound": True}).get_json()
    assert saved["sound"] is True
    assert client.get("/api/dashboards/noc").get_json()["sound"] is True
    assert "sound" not in client.put("/api/dashboards/noc", json={**body, "sound": False}).get_json()


def test_a_public_wall_does_not_hand_out_the_sound(client, anon_client):
    body = {"name": "Hall", "fit": True, "public": True, "sound": True, "sections": [{"panels": []}]}
    assert client.put("/api/dashboards/hall", json=body).status_code == 200
    board = anon_client.get("/api/dashboards/hall/public").get_json()["board"]
    assert "sound" not in board
