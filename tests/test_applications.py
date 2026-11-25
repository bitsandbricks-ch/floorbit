"""Applications (issue #1481): the built-in lists, the event's own changes, the rules the agent's
classifier gets, and what each source saw of a game."""
from floorbit import applications
from floorbit.flows.classify import Classifier
from tests.test_ports import audit_lines, sign_in


def by_id(rows):
    return {r["id"]: r for r in rows}


def test_builtin_lists_and_starter_merge():
    apps = applications.builtin()["apps"]
    # From cache-domains, with Floorbit's own sites and the published ports added.
    assert apps["steam"]["kind"] == "launcher"
    assert {"steamcontent.com", "steampowered.com"} <= set(apps["steam"]["sites"])
    assert "udp/27015-27030" in apps["steam"]["ports"]
    assert apps["steam"]["caches"] == ["steam"]
    assert apps["valorant"]["part_of"] == "riot" and apps["valorant"]["kind"] == "game"
    assert apps["streaming"]["kind"] == "sitegroup" and "twitch.tv" in apps["streaming"]["sites"]
    # Shared CDNs count for nobody.
    assert not any({"edgesuite.net", "akamaihd.net"} & set(a["sites"]) for a in apps.values())
    assert {s["id"] for s in applications.builtin()["sources"]} == {"cache-domains", "v2fly"}


def test_add_change_hide_and_reset(app_module, client):
    resp = client.post("/api/applications", json={"name": "Tournament servers", "kind": "game",
                                                  "cidr": ["198.51.100.0/28"], "ports": ["udp/27015"]})
    assert resp.status_code == 201
    own = resp.get_json()
    assert own["id"] == "tournament-servers" and own["builtin"] is False and own["cidr"] == ["198.51.100.0/28"]

    # A built-in one keeps its own sites; the event adds to them.
    resp = client.put("/api/applications/valorant", json={"sites": ["valorant.example.net", "cdn.example.org"]})
    body = resp.get_json()
    assert resp.status_code == 200 and body["edited"] is True
    assert body["sites"] == ["example.net", "example.org", "playvalorant.com"]
    assert body["added"]["sites"] == ["example.net", "example.org"]

    client.put("/api/applications/fortnite", json={"hidden": True})
    rows = by_id(client.get("/api/applications").get_json()["applications"])
    assert rows["fortnite"]["hidden"] is True and "fortnite" not in {a["id"] for a in applications.active()}

    assert client.delete("/api/applications/valorant").status_code == 200
    assert by_id(applications.listing())["valorant"]["sites"] == ["playvalorant.com"]
    assert client.delete("/api/applications/tournament-servers").status_code == 200
    assert "tournament-servers" not in by_id(applications.listing())
    assert client.delete("/api/applications/steam").status_code == 404      # nothing changed on it
    actions = [line["action"] for line in audit_lines() if line.get("area") == "applications"]
    assert actions == ["Added an application", "Changed an application", "Changed an application",
                       "Reset an application", "Removed an application"]


def test_checks_what_is_saved(client):
    def error(body, app_id=None):
        resp = client.put(f"/api/applications/{app_id}", json=body) if app_id else \
            client.post("/api/applications", json=body)
        assert resp.status_code == 400, resp.get_json()
        return resp.get_json()["error"]

    assert "name" in error({"kind": "game"})
    assert "kind" in error({"name": "X", "kind": "console"})
    assert "udp/27015" in error({"name": "X", "ports": ["27015"]})
    assert "address" in error({"name": "X", "cidr": ["not-a-net"]})
    assert "domain" in error({"name": "X", "sites": ["my-pc"]})
    assert "depot" in error({"name": "X", "depots": ["abc"]})
    assert "launcher" in error({"name": "X", "kind": "sitegroup", "part_of": "steam"})
    assert "already" in error({"name": "valorant"})
    assert client.put("/api/applications/nope", json={}).status_code == 404


def test_changing_needs_settings_manage(app_module, client):
    viewer = sign_in(app_module, "watcher", "viewer")
    assert viewer.get("/api/applications").status_code == 200
    assert viewer.post("/api/applications", json={"name": "X"}).status_code == 403
    assert viewer.put("/api/applications/steam", json={"hidden": True}).status_code == 403
    assert viewer.delete("/api/applications/steam").status_code == 403


def test_flow_rules_name_games_before_launchers(app_module, client):
    client.post("/api/applications", json={"name": "Tournament servers", "kind": "game", "cidr": ["198.51.100.0/28"]})
    servers = [{"game": "counter-strike 2", "host": "203.0.113.5"}, {"game": "Some mod", "host": "gs.example.com"}]
    rules = applications.flow_rules(servers=servers)
    assert rules[0] == {"name": "Counter-Strike 2", "category": "gaming", "cidr": ["203.0.113.5/32"]}
    names = [r["name"] for r in rules]
    assert names.index("Tournament servers") < names.index("Steam") and "Some mod" not in names
    c = Classifier()
    c.set_applications(rules)
    assert c("203.0.113.5", 17, 27015, 50000) == ("Counter-Strike 2", "gaming")
    assert c("198.51.100.3", 17, 7777, 50000) == ("Tournament servers", "gaming")
    assert c("192.0.2.9", 17, 27015, 50000) == ("Steam", "gaming")   # built-in port rules stay


def test_usage_joins_every_source():
    apps = [a for a in applications.active() if a["id"] in ("cs2", "steam", "minecraft")]
    for a in apps:
        if a["id"] == "cs2":
            a["depots"] = ["2347770"]
    seen = applications.usage(
        apps, sites={"counter-strike.net": [40, 12], "steamcontent.com": [300, 90]},
        services={"Steam": {"bytes": 5000, "seats": 80}},
        caches={"steam": {"hit_bytes": 900, "miss_bytes": 100}},
        downloads=[{"cache": "steam", "item": "depot 2347770", "hit_bytes": 600, "miss_bytes": 50}],
        servers=[{"game": "Counter-Strike 2", "status": "up", "info": {"players": 20}},
                 {"game": "cs2", "status": "up", "info": {"players": 10}},
                 {"game": "Counter-Strike 2", "status": "down", "info": {"players": 99}}])
    assert seen["cs2"] == {"lookups": 40, "dns_seats_max": 12, "traffic_bytes": None, "traffic_seats": None,
                           "cache_hit_bytes": 600, "cache_miss_bytes": 50, "players": 30}
    assert applications.seats(seen["cs2"]) == 30
    assert seen["steam"]["traffic_seats"] == 80 and seen["steam"]["cache_hit_bytes"] == 900
    assert seen["minecraft"]["lookups"] is None


def test_api_reports_usage_and_range(client):
    body = client.get("/api/applications?hours=6").get_json()
    assert body["hours"] == 6 and body["kinds"] == ["game", "launcher", "sitegroup"]
    steam = by_id(body["applications"])["steam"]
    assert set(steam["seen"]) >= {"lookups", "traffic_bytes", "cache_hit_bytes", "players", "seats"}
    assert client.get("/api/applications?hours=0").status_code == 400
