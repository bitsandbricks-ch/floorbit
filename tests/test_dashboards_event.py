"""The Event in numbers as tiles (#1045, floorbit/dashboard_event.py)."""
from floorbit import dashboard_event


def test_each_number_is_a_tile_of_its_own():
    facts = {"online": 80, "seats": 112, "online_max": 96, "downloaded": 4_200_000_000_000,
             "peak": {"bps": 9_100_000_000, "at": 1_800_000_000}, "busiest_hour": {"t": 1_800_000_000, "bps": 6e9},
             "loyal_block": {"name": "C", "share": 0.82, "hours": 11}, "cache_saved": 3_100_000_000_000,
             "games": [{"name": "Counter-Strike 2", "bar": 1.0, "seats": 142, "via": ["traffic", "dns"]},
                       {"name": "Valorant", "bar": 0.4, "seats": 61, "via": []}],
             "downloads": [{"name": "Windows updates", "bar": 1.0, "bytes": 410_000_000_000}],
             "sites": [{"name": "twitch.tv", "bar": 1.0, "seats": 201, "category": "streaming"}],
             "cache_hit_share": 0.94, "running_hours": 20.4}
    w = {t: dashboard_event.widget(t, "en", facts) for t in dashboard_event.TILES}
    assert w["event_downloaded"] == {"type": "stat", "value": 4_200_000_000_000, "unit": "B", "sub": "in 20 h"}
    assert w["event_peak"]["value"] == 9_100_000_000 and w["event_peak"]["unit"] == "bit/s"
    assert w["event_online_max"]["sub"] == "of 112 seats" and w["event_online_max"]["max"] == 112
    assert w["event_busiest_hour"]["text"] == w["event_busiest_hour"]["value"]
    assert w["event_loyal_block"]["value"] == 82 and w["event_loyal_block"]["sub"].startswith("C · ")
    games = w["event_games"]["items"]
    assert [(i["label"], i["value"]) for i in games] == [("Counter-Strike 2", "142 seats"), ("Valorant", "61 seats")]
    assert games[0]["sub"] == "Traffic + DNS" and "sub" not in games[1]
    assert w["event_downloads"]["items"][0]["value"] == "410 GB"
    assert w["event_downloads"]["sub"] == "94 % came from the LAN cache's disks"
    assert w["event_sites"]["items"][0] == {"label": "twitch.tv", "value": "201 seats", "tone": "", "number": 1.0,
                                            "max": 1, "sub": "streaming"}
    # Before anything is counted, each says so instead of a zero.
    empty = {t: dashboard_event.widget(t, "de", {}) for t in dashboard_event.TILES}
    assert all(e.get("sub") for e in empty.values())


def test_the_public_wall_is_built_from_tiles_and_follows_its_switch(client, anon_client):
    from floorbit.dashboards import BUILTIN, PUBLIC_TILES
    panes = [p["node"]["pane"] for s in BUILTIN["event"]["sections"] for p in s["panels"]]
    assert {p["kind"] for p in panes} == {"tile"}
    assert all(p["tile"] in PUBLIC_TILES for p in panes)
    # Off (the default), a screen shows that the stats wall is off, as /wall.json answers 404.
    off = anon_client.get("/api/dashboards/event/public/tiles/event_downloaded")
    assert off.status_code == 200 and off.get_json()["sub"] == "The stats wall is switched off"
    assert client.put("/api/settings", json={"public.stats_wall": True}).status_code == 200
    on = anon_client.get("/api/dashboards/event/public/tiles/event_games").get_json()
    assert on["type"] == "list" and "switched off" not in (on.get("sub") or "")
    # Public tiles, but only on a public dashboard that shows them.
    assert anon_client.get("/api/dashboards/overview/public/tiles/event_peak").status_code == 404
