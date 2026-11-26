"""Naming HTTPS flows by the DNS answers the seats got (#1600)."""
import json

from floorbit import applications
from floorbit.flows import names as names_mod
from floorbit.flows.aggregate import Aggregator
from floorbit.flows.classify import Classifier
from floorbit.flows.names import CAP, FLOOR, Names, learn_rows

NOW = 1_800_000_000
SEATS = {f"192.0.2.{10 + i}": f"A-{i + 1}" for i in range(6)}


def _https(src, dst, size=1000):
    """A download: the remote side answers from 443 to the seat's random port."""
    return {"src": src, "dst": dst, "sport": 443, "dport": 50000, "proto": 6, "bytes": size, "packets": 1}


def test_a_lookup_names_the_seats_flows_for_its_ttl():
    names = Names()
    names.learn("192.0.2.10", "example.com", [{"address": "198.51.100.7", "ttl": 300}], now=NOW)
    assert names.site_of("192.0.2.10", "198.51.100.7", now=NOW + 299) == "example.com"
    assert names.site_of("192.0.2.11", "198.51.100.7", now=NOW + 10) == "example.com"   # address-wide
    assert names.site_of("192.0.2.10", "198.51.100.7", now=NOW + 301) is None            # expired
    assert names.site_of("192.0.2.10", "198.51.100.8", now=NOW) is None


def test_the_ttl_has_a_floor_and_a_cap():
    names = Names()
    names.learn("192.0.2.10", "example.com", [{"address": "198.51.100.7", "ttl": 5}], now=NOW)
    names.learn("192.0.2.10", "example.org", [{"address": "198.51.100.8", "ttl": 86400}], now=NOW)
    names.learn("192.0.2.10", "example.net", ["198.51.100.9"], now=NOW)                   # no TTL: the floor
    assert names.site_of("192.0.2.10", "198.51.100.7", now=NOW + FLOOR) == "example.com"
    assert names.site_of("192.0.2.10", "198.51.100.8", now=NOW + CAP + 1) is None
    assert names.site_of("192.0.2.10", "198.51.100.9", now=NOW + FLOOR + 1) is None


def test_a_shared_cdn_address_names_nobody_but_the_seat_that_asked():
    names = Names()
    names.learn("192.0.2.10", "example.com", [{"address": "203.0.113.5", "ttl": 600}], now=NOW)
    names.learn("192.0.2.11", "example.org", [{"address": "203.0.113.5", "ttl": 600}], now=NOW)
    assert names.site_of("192.0.2.10", "203.0.113.5", now=NOW + 1) == "example.com"
    assert names.site_of("192.0.2.11", "203.0.113.5", now=NOW + 1) == "example.org"
    assert names.site_of("192.0.2.12", "203.0.113.5", now=NOW + 1) is None               # two sites: nobody


def test_rows_from_a_dns_plugin_are_cut_to_the_site_and_timed_when_asked():
    names = Names()
    rows = [{"ts": NOW, "domain": "cdn.download.example.com", "client": "192.0.2.10", "blocked": False,
             "answers": [{"address": "198.51.100.7", "ttl": 60}, {"address": "not an address"}]},
            {"ts": NOW, "domain": "ads.example.org", "client": "192.0.2.10", "blocked": True,
             "answers": [{"address": "0.0.0.0", "ttl": 60}]},
            {"ts": NOW, "domain": "printer.lan", "client": "192.0.2.10", "answers": ["192.0.2.99"]},
            {"ts": NOW, "domain": "example.net", "client": "192.0.2.10"},
            "not a row"]
    assert learn_rows(rows, table=names, now=NOW + 60) == 1
    assert names.site_of("192.0.2.10", "198.51.100.7", now=NOW + FLOOR) == "example.com"
    assert names.site_of("192.0.2.10", "198.51.100.7", now=NOW + FLOOR + 1) is None    # from when it was asked
    assert names.status() == {"pairs": 1, "addresses": 1, "learned": 1}


def test_the_table_stays_bounded(monkeypatch):
    monkeypatch.setattr(names_mod, "MAX_PAIRS", 3)
    monkeypatch.setattr(names_mod, "MAX_ADDRESSES", 3)
    names = Names()
    for i in range(3):
        names.learn("192.0.2.10", "example.com", [{"address": f"198.51.100.{i}", "ttl": 60}], now=NOW)
    names.learn("192.0.2.10", "example.org", [{"address": "198.51.100.9", "ttl": 60}], now=NOW + FLOOR + 1)
    assert names.status()["pairs"] == 1 and names.site_of("192.0.2.10", "198.51.100.9", now=NOW + FLOOR + 2)


def _classifier(app_module):
    c = Classifier()
    c.set_applications(applications.flow_rules())
    return c


def test_the_site_beats_the_built_in_ports_but_not_an_applications_own(app_module):
    c = _classifier(app_module)
    assert c("198.51.100.7", 6, 443, 50000) == ("Web", "web")
    assert c("198.51.100.7", 6, 443, 50000, site="steampowered.com") == ("Steam", "gaming")
    assert c("198.51.100.7", 6, 443, 50000, site="example.com") == ("Web", "web")         # no application's site
    # Minecraft's own port wins over a launcher's site on the same flow.
    assert c("198.51.100.7", 6, 25565, 50000, site="steampowered.com") == ("Minecraft", "gaming")


def test_flows_after_a_lookup_count_for_the_application_and_stay_in_the_hall(app_module):
    names = Names()
    for ip in SEATS:
        names.learn(ip, "steampowered.com", [{"address": "198.51.100.7", "ttl": 300}], now=NOW)
    agg = Aggregator(_classifier(app_module), name_of=lambda seat, remote: names.site_of(seat, remote, now=NOW))
    agg.set_seats(SEATS, dict.fromkeys(SEATS.values(), "A"))
    agg.add([_https("198.51.100.7", ip, 5000) for ip in SEATS], now=NOW)
    agg.add([_https("203.0.113.9", ip, 100) for ip in SEATS], now=NOW)                  # no lookup: Web
    snap = agg.snapshot(now=NOW + 1)
    services = {s["name"]: s for s in snap["services"]}
    assert services["Steam"]["bytes"] == 30000 and services["Steam"]["seats"] == 6
    assert services["Web"]["bytes"] == 600
    # Nothing in the summary says which seat looked up what, or which address it got.
    text = json.dumps(snap)
    assert "198.51.100.7" not in text and "steampowered.com" not in text
    for ip in SEATS:
        assert ip not in text


def test_flow_rules_carry_the_applications_sites(app_module):
    rules = {r["name"]: r for r in applications.flow_rules()}
    assert "steampowered.com" in rules["Steam"]["sites"]
    assert all("sites" in r for r in rules.values())
