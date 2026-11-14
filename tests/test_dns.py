"""DNS analytics (issue #87): hall-wide only, sites named once enough clients looked them up."""
import json

import pytest

from floorbit import dns
from floorbit.plugins import PluginError

HOUR = 1_794_650_400   # on the hour


def lookups(domain, clients, at=HOUR + 60, blocked=False):
    return [{"ts": at + i, "domain": domain, "client": f"198.51.100.{i + 1}", "blocked": blocked}
            for i in range(clients)]


@pytest.fixture
def stats(tmp_path):
    return dns.DnsStats(path=str(tmp_path / "dns.json"))


def test_site_cuts_names_and_drops_local_ones():
    assert dns.site("cdn.steamcontent.com.") == "steamcontent.com"
    assert dns.site("WWW.Example.co.uk") == "example.co.uk"
    for local in ("player-pc", "pc-7.lan", "printer.local", "10.2.0.192.in-addr.arpa", "192.0.2.1", "x" * 300,
                  "bad name.example", ""):
        assert dns.site(local) is None, local
    assert dns.category("steamcontent.com") == "gaming"
    assert dns.category("ttvnw.net") == "streaming"
    assert dns.category("example.org") == "other"


def test_a_site_is_named_only_once_enough_clients_looked_it_up(stats):
    stats.add(lookups("cdn.steamcontent.com", 5) + lookups("www.hobby.example", 4), now=HOUR + 600)
    snap = stats.snapshot(hours=1, now=HOUR + 600)
    assert [s["site"] for s in snap["sites"]] == ["steamcontent.com"]
    assert snap["lookups"] == 9
    assert snap["unnamed_lookups"] == 4
    assert snap["categories"][0] == {"id": "gaming", "lookups": 5}
    assert snap["min_clients"] == 5


def test_the_floor_is_a_setting(stats, monkeypatch):
    monkeypatch.setenv("DNS_MIN_SEATS", "3")
    stats.add(lookups("www.hobby.example", 3), now=HOUR + 600)
    assert [s["site"] for s in stats.snapshot(hours=1, now=HOUR + 600)["sites"]] == ["hobby.example"]


def test_a_closed_hour_keeps_counts_not_clients(stats, tmp_path):
    stats.add(lookups("gateway.discord.gg", 6) + lookups("www.hobby.example", 2)
              + lookups("ads.doubleclick.net", 5, blocked=True), now=HOUR + 600)
    stats.add([], now=HOUR + 3600 + 5)   # the next hour starts: the first one closes
    saved = json.loads((tmp_path / "dns.json").read_text())
    hour = saved["hours"][str(HOUR)]
    assert hour == {"lookups": 13, "blocked": 5, "sites": {"discord.gg": [6, 0, 6], "doubleclick.net": [5, 5, 5]}}
    text = (tmp_path / "dns.json").read_text()
    assert "198.51.100" not in text and "hobby" not in text
    # A new process reads the counts back.
    again = dns.DnsStats(path=str(tmp_path / "dns.json"))
    snap = again.snapshot(hours=2, now=HOUR + 3600 + 5)
    assert snap["blocked"] == 5 and snap["block_share"] == round(5 / 13, 4)
    assert [s["site"] for s in snap["blocked_sites"]] == ["doubleclick.net"]
    assert [p["lookups"] for p in snap["hours"]] == [13, 0]


def test_old_hours_are_pruned(stats, monkeypatch):
    monkeypatch.setenv("DNS_RETENTION_HOURS", "2")
    for h in range(5):
        stats.add(lookups("gateway.discord.gg", 5, at=HOUR + h * 3600), now=HOUR + h * 3600 + 100)
    stats.add([], now=HOUR + 5 * 3600)
    assert sorted(stats.hours) == [HOUR + 2 * 3600, HOUR + 3 * 3600, HOUR + 4 * 3600]


def test_new_sites_need_a_day_of_history(stats):
    stats.add(lookups("gateway.discord.gg", 5), now=HOUR + 100)
    later = HOUR + 30 * 3600
    stats.add(lookups("gateway.discord.gg", 5, at=later) + lookups("new-game.example", 5, at=later), now=later + 100)
    snap = stats.snapshot(hours=24, now=later + 100)
    assert [s["site"] for s in snap["new"]] == ["new-game.example"]


def test_poll_reads_each_plugin_after_its_cursor(stats):
    class Spec:
        def __init__(self, id):
            self.id = self.name = id

    asked = []

    class Registry:
        def feeders(self, area):
            return [Spec("resolver"), Spec("broken")] if area == "dns" else []

        def call(self, spec, method, since):
            asked.append((spec.id, method, since))
            if spec.id == "broken":
                raise PluginError("no answer")
            return [*lookups("cdn.steamcontent.com", 5, at=HOUR + 60), "junk", {"ts": "x"}]

    stats.registry = Registry()
    stats.poll_once(now=HOUR + 120)
    stats.poll_once(now=HOUR + 180)
    assert asked[0] == ("resolver", "dns_queries", HOUR + 120 - 120)
    assert asked[2] == ("resolver", "dns_queries", HOUR + 64)    # the newest lookup seen
    snap = stats.snapshot(hours=1, now=HOUR + 180)
    assert snap["lookups"] == 5                                   # the second poll's are older: not again
    assert snap["error"] == "broken: no answer" and snap["plugins"] == 2


def test_dns_is_a_plugin_area():
    from floorbit.plugins import AREA_METHODS, AREAS
    assert AREA_METHODS["dns"] == ("dns_queries",) and "dns" in AREAS


def test_api(client, app_module):
    app_module.app.extensions["floorbit_dns"].stop()
    r = client.get("/api/dns?hours=6")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["hours"]) == 6 and body["min_clients"] == 5
    assert client.get("/api/dns?hours=0").status_code == 400
    assert client.get("/api/dns?hours=lots").status_code == 400
    assert client.get("/dns").status_code in (200, 503)   # 503 only when the React app isn't built


def test_the_demo_hall_looks_things_up():
    import time

    from floorbit.builtin_plugins.demo.plugin import Plugin
    demo = Plugin.__new__(Plugin)
    got = demo.dns_queries(time.time() - 120)
    assert got and all(e["client"].startswith("192.0.2.") for e in got)
    stats = dns.DnsStats(path="/dev/null/never")
    stats._save = lambda: None
    stats.add(got)
    names = {s["site"] for s in stats.snapshot(hours=1)["sites"]}
    assert "steamcontent.com" in names and not any("hobby" in n for n in names)
