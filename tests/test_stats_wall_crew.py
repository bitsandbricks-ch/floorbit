"""The stats wall setting is about the public side: crew always read the numbers (#1113)."""


def test_crew_read_the_numbers_while_the_public_wall_is_off(client, anon_client):
    assert anon_client.get("/wall.json").status_code == 404
    assert client.get("/wall.json").status_code == 200
    tile = client.get("/api/dashboard/floorbit/event_downloaded").get_json()
    assert "switched off" not in (tile.get("sub") or "")
    off = anon_client.get("/api/dashboards/event/public/tiles/event_downloaded").get_json()
    assert off["sub"] == "The stats wall is switched off"
