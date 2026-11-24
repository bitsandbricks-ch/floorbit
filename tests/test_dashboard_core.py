"""Floorbit's own dashboard tiles (issue #302): problems and incidents with no plugin set up."""

import pytest

from floorbit import dashboard_core
from floorbit.plugins import validate
from floorbit.plugins.widgets import check_widget
from tests.conftest import TEST_USER


def _login(app_module, name, role):
    app_module.app.extensions["auth"].users.add(name, f"{name}-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": name, "password": f"{name}-password-1"}).status_code == 302
    return c


def test_the_tiles_come_first_and_work_like_plugin_widgets(client):
    tiles = client.get("/api/dashboard").get_json()["tiles"]
    core = [t for t in tiles if t["plugin"] == "floorbit"]
    assert [t["id"] for t in core][:2] == ["problems", "incidents"] and tiles[:len(core)] == core
    assert core[0]["url"] == "/api/dashboard/floorbit/problems" and core[0]["plugin_name"] == "Floorbit"
    body = client.get(core[0]["url"]).get_json()
    assert body["type"] == "stat" and body["link"] == "/problems" and body["unit"] == "down"
    assert "port trouble" in body["sub"] and "muted" in body["sub"]
    assert client.get("/api/dashboard/floorbit/nope").status_code == 404


def test_the_incident_tile_counts_open_and_waiting(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    old = client.post("/api/incidents", json={"seat": "A-1", "title": "No link"}).get_json()
    client.post("/api/incidents", json={"seat": "A-2", "title": "Slow"})
    taken = client.post("/api/incidents", json={"seat": "A-3", "title": "Power"}).get_json()
    client.patch(f"/api/incidents/{taken['id']}", json={"assignee": TEST_USER})
    body = client.get("/api/dashboard/floorbit/incidents").get_json()
    assert body["value"] == 2 and body["tone"] == "" and body["sub"] == "0 waiting 10+ min · 1 being worked"
    with client.application.app_context():
        later = dashboard_core.incidents_widget("en", now=old["created_at"] + 11 * 60)
    assert later["tone"] == "warn" and later["sub"].startswith("2 waiting")


def test_texts_follow_the_browser_language(client):
    tiles = client.get("/api/dashboard", headers={"Accept-Language": "de-CH,de;q=0.9"}).get_json()["tiles"]
    assert [t["label"] for t in tiles[:4]] == ["Probleme jetzt", "Störungen", "Switches", "Plätze online"]
    body = client.get("/api/dashboard/floorbit/incidents", headers={"Accept-Language": "de-CH"}).get_json()
    assert body["unit"] == "offen" and "in Arbeit" in body["sub"]


def test_only_people_who_see_the_board_get_the_incident_tile(app_module, client):
    viewer = _login(app_module, "vic", "viewer")
    tiles = viewer.get("/api/dashboard").get_json()["tiles"]
    assert [t["id"] for t in tiles if t["plugin"] == "floorbit"] == [
        "problems", "switches", "seats", "down", "switch_states", "traffic", "seats_by_block", "seats_by_row",
        *STATS_TILES]
    assert viewer.get("/api/dashboard/floorbit/incidents").status_code == 404
    assert viewer.get("/api/dashboard/floorbit/open_incidents").status_code == 404
    assert viewer.get("/api/dashboard/floorbit/problems").status_code == 200


def test_no_plugin_may_take_the_id():
    assert "taken" in validate({"id": "floorbit", "uses": ["widgets"]})


def test_switch_and_seat_tiles(client):
    ids = [t["id"] for t in client.get("/api/dashboard").get_json()["tiles"] if t["plugin"] == "floorbit"]
    assert ids == ["problems", "incidents", "switches", "seats", "down", "switch_states", "open_incidents", "traffic",
                   "seats_by_block", "seats_by_row", *STATS_TILES]
    assert dashboard_core.switches_widget("en", {"online": 40, "offline": 2, "unknown": 1}) == {
        "type": "stat", "value": 40, "unit": "of 43 up", "tone": "err", "sub": "2 offline · 1 not known",
        "link": "/problems", "min": 0, "max": 43}
    assert dashboard_core.switches_widget("en", {"online": 3, "offline": 0, "unknown": 0})["tone"] == "ok"
    assert dashboard_core.switches_widget("de", {"online": 0, "offline": 0, "unknown": 0})["unit"] == "von 0 online"
    unknown = dashboard_core.seats_widget("en", None, 120)
    assert unknown["value"] == "?" and unknown["unit"] == "of 120, all halls" and "Not known" in unknown["sub"]
    assert dashboard_core.seats_widget("en", 87, 120)["value"] == 87
    for tile in ("switches", "seats"):
        assert client.get(f"/api/dashboard/floorbit/{tile}").get_json()["type"] == "stat"


def test_down_switches_tile_lists_what_is_down_and_for_how_long(client):
    now = 10_000
    statuses = {
        "a": {"id": "a", "name": "sw-a-01", "status": "offline", "since": now - 2 * 3600 - 5 * 60},
        "b": {"id": "b", "name": "sw-b-01", "status": "offline", "since": now - 7 * 60},
        "c": {"id": "c", "name": "sw-c-01", "status": "online", "since": now - 60},
        "d": {"id": "d", "name": "sw-d-01", "status": "offline", "since": now - 10},
    }
    body = dashboard_core.down_widget("en", statuses, now=now)
    assert body == {"type": "list", "items": [
        {"label": "sw-a-01", "value": "2 h 5 min", "tone": "err", "device": "a"},
        {"label": "sw-b-01", "value": "7 min", "tone": "err", "device": "b"},
        {"label": "sw-d-01", "value": "just now", "tone": "err", "device": "d"}]}
    assert dashboard_core.down_widget("de", statuses, now=now)["items"][1]["value"] == "7 Min."
    # The device id survives the widget check, so a large widget can open the switch's glance (#925).
    assert check_widget(body, {"id": "down"})["items"][0]["device"] == "a"
    states = check_widget(dashboard_core.switch_states_widget("en", statuses, now=now), {"id": "s"})
    assert [i.get("device") for i in states["items"]] == ["a", "b", "d", "c"]
    up = dashboard_core.down_widget("en", {"c": statuses["c"]}, now=now)
    assert up["items"] == [{"label": "All switches up", "state": "up"}]
    assert dashboard_core.down_widget("de", {}, now=now)["items"][0]["state"] == "unknown"
    many = {str(n): {"id": str(n), "name": f"sw-{n:02d}", "status": "offline", "since": now - n} for n in range(25)}
    items = dashboard_core.down_widget("en", many, now=now)["items"]
    assert len(items) == dashboard_core.MAX_DOWN + 1 and items[-1]["label"] == "+ 5 more"
    body = client.get("/api/dashboard/floorbit/down").get_json()
    assert body["type"] == "status" and body["refresh"] == 15   # no monitor in the tests: no status yet


def test_switch_states_put_down_switches_first():
    statuses = {"a": {"id": "a", "name": "sw-a-01", "status": "online", "since": 0},
                "b": {"id": "b", "name": "sw-b-03", "status": "offline", "since": 1000},
                "c": {"id": "c", "name": "sw-c-02", "status": "unknown", "since": 0}}
    body = dashboard_core.switch_states_widget("en", statuses, now=1000 + 4 * 60)
    assert body["type"] == "status"
    assert [(i["label"], i["state"]) for i in body["items"]] == [
        ("sw-b-03", "down"), ("sw-c-02", "unknown"), ("sw-a-01", "up")]
    assert body["items"][0]["detail"] == "down 4 min" and body["items"][2]["detail"] == ""


def test_open_incidents_are_a_table_oldest_first(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    client.post("/api/incidents", json={"seat": "A-1", "title": "No link"})
    client.post("/api/incidents", json={"seat": "A-2", "title": "Slow"})
    body = client.get("/api/dashboard/floorbit/open_incidents").get_json()
    assert body["type"] == "table" and [c["key"] for c in body["columns"]] == ["what", "where", "open"]
    assert [(r["what"], r["where"]) for r in body["rows"]] == [("No link", "Seat A-1"), ("Slow", "Seat A-2")]
    de = client.get("/api/dashboard/floorbit/open_incidents", headers={"Accept-Language": "de-CH"}).get_json()
    assert de["columns"][0]["label"] == "Was" and de["rows"][0]["where"] == "Platz A-1"


def test_traffic_is_two_lines_over_time():
    snap = {"series": [{"t": 100, "down": 5e9, "up": 1e9, "online": 3},
                       {"t": 160, "down": 6e9, "up": 2e9, "online": 3}]}
    body = dashboard_core.traffic_widget("en", snap)
    assert body["type"] == "series" and body["unit"] == "bit/s"
    assert [s["label"] for s in body["series"]] == ["Download", "Upload"]
    assert body["series"][0]["points"] == [[100, 5e9], [160, 6e9]]


def test_the_traffic_tile_answers_with_no_reads_yet(client):
    body = client.get("/api/dashboard/floorbit/traffic").get_json()
    assert body["type"] == "series" and all(v == 0 for s in body["series"] for _t, v in s["points"])


def test_seats_by_block_are_numbers_out_of_each_block():
    blocks = {"B": {"B1", "B2"}, "A": {"A1", "A2", "A3"}, "A10": {"A101"}}
    body = dashboard_core.seats_by_block_widget("en", blocks, {"A1", "A3", "B2"})
    assert [i["label"] for i in body["items"]] == ["A", "B", "A10"]
    assert body["items"][0] == {"label": "A", "value": "2 / 3", "number": 2, "max": 3}
    assert check_widget(body, {"id": "x"})["items"][0]["number"] == 2


def test_seats_by_block_say_when_nobody_knows():
    body = dashboard_core.seats_by_block_widget("de", {"A": {"A1"}}, None)
    assert body["items"] == [{"label": "A", "value": "? / 1"}]
    assert body["sub"].startswith("Gerade nicht bekannt")


STATS_TILES = ["bandwidth", "peak", "ports", "uplinks", "top_ports", "traffic_mix", "flow_services", "traffic_areas",
               "anomalies", "service_health", "internet_uplinks", "lancache", "power_circuits", "agents",
               "dns_lookups", "dns_sites", "dns_blocked", "launchers", "wifi_clients", "wifi_aps",
               # The Event in numbers (#1045, dashboard_event.py).
               "event_downloaded", "event_peak", "event_online_max", "event_busiest_hour", "event_loyal_block",
               "event_cache_saved", "event_games"]
SNAP = {"now": {"t": 160, "down": 4.8e9, "up": 9.4e9, "online": 93,
                "ports_up": 138, "ports_down": 598, "ports_errors": 1},
        "peak": {"bps": 16e9, "at": 100}, "day": {"peak_bps": 15.5e9},
        "uplinks": [{"switch": "sw-a", "port": "Te1/1", "utilization": 0.5, "bps": 5e9},
                    {"switch": "sw-b", "port": "Te1/1", "utilization": 0.85, "bps": 8.5e9}],
        "top": [{"switch": "sw-a", "port": "Gi1/0/3", "seat": "A-3", "nick": "someone", "bps": 9e8},
                {"switch": "sw-b", "port": "Gi1/0/9", "seat": None, "bps": 2e8}]}


def test_the_stats_view_is_split_into_tiles():
    bw = dashboard_core.bandwidth_widget("en", SNAP)
    assert (bw["value"], bw["unit"], bw["sub"]) == (14.2e9, "bit/s", "↓ 4.8 Gbit/s · ↑ 9.4 Gbit/s")
    peak = dashboard_core.peak_widget("en", SNAP, now=100 + 13 * 60)
    assert peak["value"] == 16e9 and peak["sub"] == "13 min ago · 24 h peak 16 Gbit/s"
    ports = dashboard_core.ports_widget("de", SNAP)
    assert (ports["value"], ports["tone"], ports["sub"]) == (138, "warn", "598 offline · 1 mit Fehlern")
    up = dashboard_core.uplinks_widget("en", SNAP)["items"]
    assert up[0] == {"label": "sw-b Te1/1", "value": "85 % · 8.5 Gbit/s", "number": 85, "max": 100, "tone": "err"}
    top = dashboard_core.top_ports_widget("en", SNAP)["items"]
    # Seat numbers, never nicks: a dashboard may hang where anyone walks past.
    assert [i["label"] for i in top] == ["Seat A-3", "sw-b Gi1/0/9"] and "someone" not in str(top)
    for widget in (bw, peak, ports):
        check_widget(widget, {"id": "x"})


def test_stats_tiles_say_when_nothing_was_read():
    assert dashboard_core.bandwidth_widget("en", {})["sub"] == "No traffic read yet"
    assert dashboard_core.peak_widget("en", {})["value"] == "\u2013"
    assert dashboard_core.uplinks_widget("en", {})["items"] == []


FLOWS = {"mix_hour": {"gaming": 300, "web": 700}, "services": [{"name": "Steam", "category": "downloads", "seats": 12,
                                                                 "bytes": 2e11}],
         "areas": [{"area": "Block A", "bytes": 5e11}],
         "anomalies": [{"kind": "p2p", "title": "P2P", "detail": "seat D-5", "first_seen": 100},
                       {"kind": "rogue-dhcp", "title": "Rogue DHCP", "detail": "", "first_seen": 200}]}


def test_the_traffic_view_is_split_into_tiles():
    mix = dashboard_core.traffic_mix_widget("de", FLOWS)
    assert [(i["label"], i["value"]) for i in mix["items"]] == [("Gaming", "30 % · 300 B"), ("Web", "70 % · 700 B")]
    assert mix["sub"] == "Letzte Stunde: 1.0 kB"
    assert dashboard_core.flow_services_widget("en", FLOWS)["items"][0]["value"] == "200 GB · 12 seats"
    assert dashboard_core.traffic_areas_widget("en", FLOWS)["items"][0]["number"] == 5e11
    odd = dashboard_core.anomalies_widget("en", FLOWS, now=260)["items"]
    assert [(i["label"], i["state"]) for i in odd] == [("Rogue DHCP", "down"), ("P2P · seat D-5", "warn")]
    assert dashboard_core.anomalies_widget("en", {"anomalies": []})["items"][0]["state"] == "up"
    assert dashboard_core.traffic_mix_widget("en", None)["sub"] == "No flows yet"


def test_the_service_views_are_split_into_tiles():
    wall = {"checks": [{"name": "DNS", "status": "up", "summary": "12 ms"},
                       {"name": "fw-03", "status": "down", "summary": "1 range failed over"},
                       {"name": "odd", "status": "sideways", "summary": ""}]}
    items = dashboard_core.service_health_widget("en", wall)["items"]
    assert [(i["label"], i["state"]) for i in items] == [("fw-03", "down"), ("odd", "unknown"), ("DNS", "up")]
    assert dashboard_core.service_health_widget("de", {})["sub"] == "Noch nichts geprüft"
    ups = dashboard_core.internet_uplinks_widget("en", {"uplinks": [
        {"name": "ISP 1", "status": "up", "utilization": 0.65, "in_bps": 6.5e9, "out_bps": 1e9},
        {"name": "ISP 2", "status": "down"}]})["items"]
    assert ups[0] == {"label": "ISP 1", "number": 65, "max": 100, "value": "65 % · ↓ 6.5 Gbit/s · ↑ 1.0 Gbit/s",
                      "tone": "warn"}
    assert ups[1]["tone"] == "err" and ups[1]["value"] == "down"
    cache = dashboard_core.lancache_widget("en", {"configured": True, "hit_ratio": 0.7193, "hit_bytes": 8e11,
                                                  "miss_bytes": 3e11})
    assert (cache["value"], cache["unit"]) == (71.9, "%")
    assert cache["sub"] == "800 GB from the cache · 300 GB from the internet"
    assert dashboard_core.lancache_widget("en", {})["sub"] == "No LAN cache set up"
    power = dashboard_core.power_circuits_widget("en", {"warn": 80, "crit": 95, "circuits": [
        {"name": "C1", "load_pct": 50}, {"name": "C2", "load_pct": 96.4},
        {"name": "C3", "state": "tripped", "load_pct": 0}, {"name": "C4", "load_pct": None}]})["items"]
    assert [(i["label"], i.get("tone", "")) for i in power] == [("C2", "err"), ("C1", ""), ("C3", "err"), ("C4", "")]
    agents = dashboard_core.agents_widget("en", [{"connected": True}, {"connected": False, "outdated": True}])
    assert (agents["value"], agents["unit"], agents["tone"]) == (1, "of 2 online", "err")
    assert agents["sub"] == "1 need an update"
    assert dashboard_core.agents_widget("en", [])["sub"] == "No agent yet"


def test_dns_games_and_wifi_are_split_into_tiles():
    dns = {"lookups": 576, "blocked": 44, "block_share": 0.0764,
           "sites": [{"site": "steamcontent.com", "lookups": 120}],
           "blocked_sites": [{"site": "ads.example", "blocked": 32}]}
    assert dashboard_core.dns_lookups_widget("en", dns)["sub"] == "44 blocked (7.6 %) in 24 h"
    assert dashboard_core.dns_lookups_widget("de", None)["sub"] == "Noch keine DNS-Logs"
    assert dashboard_core.dns_sites_widget("en", dns)["items"] == [
        {"label": "steamcontent.com", "value": "120 lookups", "number": 120}]
    assert dashboard_core.dns_blocked_widget("en", dns)["items"][0]["number"] == 32
    games = {"launchers": [{"name": "Epic", "cache_hit_bytes": 1e9, "cache_miss_bytes": 0, "traffic_seats": 3},
                           {"name": "Steam", "cache_hit_bytes": 4.5e11, "cache_miss_bytes": 1e11, "traffic_seats": 17}]}
    items = dashboard_core.launchers_widget("en", games)["items"]
    assert [i["label"] for i in items] == ["Steam", "Epic"] and items[0]["value"] == "450 GB from the cache · 17 seats"
    wifi = {"clients": 289, "bands": {"2.4": {"clients": 70}, "5": {"clients": 219}},
            "aps": [{"name": "ap-01", "status": "up", "clients": 19}, {"name": "ap-stage", "status": "up", "busy": True,
                                                                         "clients": 40},
                    {"name": "ap-02", "status": "down", "clients": 0}]}
    assert dashboard_core.wifi_clients_widget("en", wifi)["sub"] == "2.4 GHz: 70 · 5 GHz: 219"
    aps = dashboard_core.wifi_aps_widget("en", wifi)["items"]
    assert [(a["label"], a["state"]) for a in aps] == [("ap-02", "down"), ("ap-stage", "warn"), ("ap-01", "up")]
    assert aps[1]["detail"] == "40 clients · busy"
    assert dashboard_core.wifi_aps_widget("en", {})["sub"] == "No Wi-Fi data yet"


@pytest.mark.parametrize("tile", STATS_TILES)
def test_every_stats_tile_answers(client, tile):
    body = client.get(f"/api/dashboard/floorbit/{tile}").get_json()
    assert body["type"] in ("stat", "list", "status"), body


def test_traffic_tiles_go_with_the_traffic_feature(client, monkeypatch):
    from floorbit import features
    monkeypatch.setattr(features, "off", lambda data=None: {"traffic"})
    ids = [t["id"] for t in client.get("/api/dashboard").get_json()["tiles"]]
    assert "traffic_mix" not in ids and "bandwidth" in ids
    assert client.get("/api/dashboard/floorbit/anomalies").status_code == 404


def test_the_seats_by_block_tile_answers(client):
    body = client.get("/api/dashboard/floorbit/seats_by_block").get_json()
    assert body["type"] == "list"


def test_a_block_named_by_its_rows_counts_and_its_rows_have_a_tile(client):
    """#1078: a block without a name shows as its row letters, and each row has its own bar."""
    client.post("/api/seat-blocks", json={"name": "", "x": 10, "y": 10, "cols": 3, "rows": 2, "naming": "rows",
                                          "row_start": "C"})
    client.post("/api/seat-blocks", json={"name": "A", "x": 40, "y": 10, "cols": 2, "rows": 2})
    blocks = client.get("/api/dashboard/floorbit/seats_by_block").get_json()["items"]
    assert sorted(i["label"] for i in blocks) == ["A", "C\u2013D"]
    rows = client.get("/api/dashboard/floorbit/seats_by_row").get_json()
    # "? / 3" or "0 / 3": whether a port read happened yet doesn't matter here.
    assert rows["type"] == "list" and [(i["label"], i["value"][-3:]) for i in rows["items"]] == [
        ("C", "/ 3"), ("D", "/ 3"), ("A 1", "/ 2"), ("A 2", "/ 2")]


def test_seats_by_row_count_each_row_out_of_its_seats():
    rows = [{"name": "C", "naming": "rows", "block_label": "C\u2013D", "seats": ["C-1", "C-2"]},
            {"name": "2", "naming": "block", "block_label": "A", "seats": ["A-3", "A-4"]}]
    body = dashboard_core.seats_by_row_widget("en", rows, {"C-2", "A-3", "A-4"})
    assert body["items"] == [{"label": "C", "value": "1 / 2", "number": 1, "max": 2},
                             {"label": "A 2", "value": "2 / 2", "number": 2, "max": 2}]


def test_switch_and_seat_stats_carry_their_scale_for_a_gauge():
    body = dashboard_core.switches_widget("en", {"online": 3, "offline": 1, "unknown": 0})
    assert (body["min"], body["max"]) == (0, 4)


def test_the_traffic_tile_shows_a_time_range_and_yesterday():
    now = 1_800_000_000
    snap = {"series": [{"t": now - 7200 + i * 60, "down": i, "up": 1, "online": 0} for i in range(121)]}
    hours = [{"t": now - 86400 - 3600, "avg_bps": 5, "peak_bps": 9, "online_max": 0},
             {"t": now - 86400 - 1800, "avg_bps": 6, "peak_bps": 9, "online_max": 0},
             {"t": now - 3600, "avg_bps": 7, "peak_bps": 11, "online_max": 0}]
    w = dashboard_core.traffic_widget("en", snap, "1h", None, (), now)
    assert [len(s["points"]) for s in w["series"]] == [61, 61] and w["series"][0]["points"][0][0] == now - 3600
    w = dashboard_core.traffic_widget("en", snap, "1h", "day", hours, now)
    ghost = w["series"][-1]
    assert ghost["ghost"] is True and ghost["label"] == "Yesterday (in + out)"
    assert ghost["points"] == [[now - 3600, 5], [now - 1800, 6]]
    w = dashboard_core.traffic_widget("de", snap, "event", None, hours, now)
    assert [s["label"] for s in w["series"]] == ["Durchschnitt (rein + raus)", "Spitze (rein + raus)"]
    assert w["series"][1]["points"][-1] == [now - 3600, 11]
    many = [[i, i] for i in range(1000)]
    assert len(dashboard_core._buckets(many)) == dashboard_core.MAX_POINTS


def test_a_pane_asks_the_traffic_tile_for_its_range(client):
    tiles = client.get("/api/dashboard").get_json()["tiles"]
    assert next(t for t in tiles if t["id"] == "traffic")["ranges"] is True
    assert "ranges" not in next(t for t in tiles if t["id"] == "seats")
    assert client.get("/api/dashboard/floorbit/traffic?range=24h&compare=day").status_code == 200
    assert client.get("/api/dashboard/floorbit/traffic?range=event").get_json()["type"] == "series"


def test_the_traffic_tile_marks_what_happened(client):
    now = 1_800_000_000
    switches = [[now - 50, "s1", "sw-a-01", "offline"], [now - 10, "s1", "sw-a-01", "online"]]
    marks = dashboard_core.event_marks("en", switches, [{"created_at": now - 30, "title": "Port flapping"}])
    assert [(m["label"], m["tone"]) for m in marks] == [
        ("sw-a-01 down", "err"), ("Incident: Port flapping", "warn"), ("sw-a-01 back", "ok")]
    widget = {"series": [{"label": "Down", "points": [[now - 40, 1], [now, 2]]}]}
    assert [m["label"] for m in dashboard_core.with_marks(widget, marks)["marks"]] == [
        "Incident: Port flapping", "sw-a-01 back"]   # the one before the lines start is left out
    assert "marks" not in dashboard_core.with_marks({"series": []}, marks)
    tile = next(t for t in client.get("/api/dashboard").get_json()["tiles"] if t["id"] == "traffic")
    assert tile["marks"] is True
    assert client.get("/api/dashboard/floorbit/traffic?marks=1").status_code == 200
