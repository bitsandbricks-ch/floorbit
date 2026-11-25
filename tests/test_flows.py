"""Traffic insights from NetFlow/IPFIX (issue #25). Packets are built here byte by byte; no exporter."""
import gzip
import ipaddress
import json
import os
import struct

import pytest

from floorbit.flows import aggregate, classify, parse, store
from floorbit.flows.aggregate import Aggregator
from floorbit.flows.classify import Classifier, compile_rules
from floorbit.flows.collector import Collector

SEATS = {f"192.0.2.{10 + i}": f"A-{i + 1}" for i in range(8)}
AREAS = dict.fromkeys(SEATS.values(), "A")
NOW = 1_800_000_000


def ip(a):
    return ipaddress.ip_address(a).packed


# ── sample packets ────────────────────────────────────────────────────────────────────────
def v5(records, secs=NOW, uptime=600_000, sampling=0):
    head = struct.pack("!HHIIIIBBH", 5, len(records), uptime, secs, 0, 1, 0, 0, sampling)
    body = b"".join(struct.pack("!4s4s4sHHIIIIHHBBBBHHBBH", ip(r["src"]), ip(r["dst"]), ip("0.0.0.0"), 1, 2,
                                r["packets"], r["bytes"], uptime - 5000, uptime - 1000, r["sport"], r["dport"],
                                0, 0, r["proto"], 0, 0, 0, 0, 0, 0) for r in records)
    return head + body


V9_FIELDS = [(8, 4), (12, 4), (7, 2), (11, 2), (4, 1), (1, 4), (2, 4), (21, 4)]
IPFIX_FIELDS = [(27, 16), (28, 16), (7, 2), (11, 2), (4, 1), (1, 8), (2, 8), (153, 8)]


def v9(records, template=True, data=True, source_id=7, uptime=600_000):
    sets = b""
    if template:
        t = struct.pack("!HH", 256, len(V9_FIELDS)) + b"".join(struct.pack("!HH", f, n) for f, n in V9_FIELDS)
        sets += struct.pack("!HH", 0, 4 + len(t)) + t
    if data:
        rows = b"".join(ip(r["src"]) + ip(r["dst"]) + struct.pack("!HHBIII", r["sport"], r["dport"], r["proto"],
                                                                  r["bytes"], r["packets"], uptime - 1000)
                        for r in records)
        rows += b"\0" * (-len(rows) % 4)    # padding
        sets += struct.pack("!HH", 256, 4 + len(rows)) + rows
    return struct.pack("!HHIIII", 9, len(records), uptime, NOW, 1, source_id) + sets


def ipfix(records, domain=1):
    t = struct.pack("!HH", 300, len(IPFIX_FIELDS) + 1) + b"".join(struct.pack("!HH", f, n) for f, n in IPFIX_FIELDS)
    t += struct.pack("!HHI", 0x8000 | 12, 0xFFFF, 9)    # an enterprise field with variable length
    sets = struct.pack("!HH", 2, 4 + len(t)) + t
    rows = b"".join(ip(r["src"]) + ip(r["dst"]) + struct.pack("!HHBQQQ", r["sport"], r["dport"], r["proto"],
                                                              r["bytes"], r["packets"], NOW * 1000)
                    + b"\x03abc" for r in records)
    sets += struct.pack("!HH", 300, 4 + len(rows)) + rows
    return struct.pack("!HHIII", 10, 16 + len(sets), NOW, 1, domain) + sets


def rec(src, dst, sport, dport, proto=17, size=1000, packets=1):
    return {"src": src, "dst": dst, "sport": sport, "dport": dport, "proto": proto, "bytes": size, "packets": packets}


STEAM = rec("203.0.113.30", "192.0.2.10", 27015, 50000, size=5_000_000, packets=4000)


# ── parsing ───────────────────────────────────────────────────────────────────────────────
def test_netflow_v5():
    [f] = parse.parse(v5([STEAM]))
    assert (f["src"], f["dst"], f["sport"], f["dport"], f["proto"]) == ("203.0.113.30", "192.0.2.10", 27015, 50000, 17)
    assert f["bytes"] == 5_000_000 and f["packets"] == 4000 and f["end"] == NOW - 1


def test_netflow_v5_sampling_scales_up():
    [f] = parse.parse(v5([STEAM], sampling=(1 << 14) | 100))
    assert f["bytes"] == 500_000_000


def test_netflow_v9_needs_its_template_first():
    templates = parse.Templates()
    assert parse.parse(v9([STEAM], template=False), "198.51.100.1", templates) == []
    assert templates.missing == 1
    parse.parse(v9([], data=False), "198.51.100.1", templates)
    [f] = parse.parse(v9([STEAM], template=False), "198.51.100.1", templates)
    assert f["dst"] == "192.0.2.10" and f["bytes"] == 5_000_000 and f["end"] == NOW - 1
    # Templates are per exporter: another router's data isn't read with this one's.
    assert parse.parse(v9([STEAM], template=False), "198.51.100.2", templates) == []


def test_ipfix_with_ipv6_and_variable_length_fields():
    a = rec("2001:db8::30", "2001:db8:1::10", 443, 51000, proto=6, size=10**10, packets=5)
    b = rec("2001:db8::31", "2001:db8:1::11", 80, 51001, proto=6, size=7, packets=1)
    flows = parse.parse(ipfix([a, b]), "198.51.100.1", parse.Templates())
    assert [(f["src"], f["bytes"], f["end"]) for f in flows] == [
        ("2001:db8::30", 10**10, NOW), ("2001:db8::31", 7, NOW)]


@pytest.mark.parametrize("data", [b"", b"\x00\x05", b"\x00\x07" + b"\0" * 30, v9([STEAM]) + b"\x01\x00\x00\xff"])
def test_garbage_is_refused(data):
    with pytest.raises(parse.ParseError):
        parse.parse(data, "198.51.100.1", parse.Templates())


def _v9_template(fields, template_id=256):
    t = struct.pack("!HH", template_id, len(fields)) + b"".join(struct.pack("!HH", f, n) for f, n in fields)
    return struct.pack("!HH", 0, 4 + len(t)) + t


def test_a_template_of_empty_fields_does_not_hang_the_collector():
    # 40 bytes from anyone on the network: the record loop never moved on, and grew a list until
    # the process ran out of memory (on the agent, that is the agent).
    sets = _v9_template([(1, 0)]) + struct.pack("!HH", 256, 8) + b"\0" * 4
    packet = struct.pack("!HHIIII", 9, 1, 0, NOW, 1, 7) + sets
    assert parse.parse(packet, "198.51.100.1", parse.Templates()) == []


@pytest.mark.parametrize("cut", [30, 34, 42])
def test_a_template_cut_short_is_a_parse_error(cut):
    # Before: struct.error, which the collector didn't catch: one packet stopped the listener for good.
    packet = struct.pack("!HHIIII", 9, 1, 0, NOW, 1, 7) + _v9_template(V9_FIELDS)
    packet = packet[:20] + struct.pack("!HH", 0, cut - 20) + packet[24:cut]
    with pytest.raises(parse.ParseError):
        parse.parse(packet, "198.51.100.1", parse.Templates())


def test_made_up_templates_cannot_fill_memory(monkeypatch):
    monkeypatch.setattr(parse, "MAX_TEMPLATES", 50)
    templates = parse.Templates()
    parse.parse(v9([], data=False), "198.51.100.1", templates)        # the real router's
    for n in range(200):
        parse.parse(struct.pack("!HHIIII", 9, 1, 0, NOW, 1, n) + _v9_template([(8, 4)]), "192.0.2.99", templates)
    assert len(templates.known) == 50
    parse.parse(v9([], data=False), "198.51.100.1", templates)        # sent again, as routers do
    assert parse.parse(v9([STEAM], template=False), "198.51.100.1", templates)


def test_the_collector_keeps_publishing_after_the_clock_goes_back(tmp_path):
    sent = []
    col = Collector(Aggregator(Classifier()), store.RawStore(str(tmp_path)), log=lambda *_: None)
    col.publish = sent.append
    col.housekeeping(now=NOW, refresh_seats=lambda: (SEATS, AREAS))
    col.housekeeping(now=NOW - 3600, refresh_seats=lambda: (SEATS, AREAS))   # NTP stepped back an hour
    assert len(sent) == 2



@pytest.mark.parametrize("allow,sent_from,counted", [
    ("", "198.51.100.66", True),                              # unset: everyone, as before
    ("198.51.100.1, 192.0.2.0/28", "198.51.100.1", True),
    ("198.51.100.1, 192.0.2.0/28", "192.0.2.14", True),
    ("198.51.100.1, 192.0.2.0/28", "198.51.100.66", False),   # a seat PC forging flows
    ("not-an-address", "198.51.100.1", False),                # only typos: nobody, not everybody
])
def test_only_listed_exporters_count(allow, sent_from, counted, tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWS_ALLOW", allow)
    col = Collector(Aggregator(Classifier()), store.RawStore(str(tmp_path)), log=lambda *_: None)
    assert (col.receive(v5([STEAM]), sent_from, now=NOW) == 1) is counted
    assert col.refused == (0 if counted else 1)
    sent = []
    col.publish = sent.append
    col.housekeeping(now=NOW, refresh_seats=lambda: (SEATS, AREAS))
    assert sent[0]["refused"] == col.refused


# ── classifying ───────────────────────────────────────────────────────────────────────────
def test_builtin_ports_and_own_rules_first():
    c = Classifier()
    assert c("203.0.113.30", 17, 27015, 50000) == ("Steam", "gaming")
    assert c("203.0.113.30", 6, 443, 51000) == ("Web", "web")
    assert c("203.0.113.30", 17, 443, 5100) == ("Web", "web")   # a QUIC client's port isn't a Riot game
    assert c("203.0.113.30", 6, 51000, 1935) == ("RTMP streaming", "streaming")   # the seat serves
    assert c("203.0.113.30", 6, 9, 9) == ("Other", "other")
    own = Classifier(compile_rules([{"name": "LAN cache", "category": "downloads", "cidr": ["198.51.100.50/32"]}])
                     + compile_rules(classify.BUILTIN))
    assert own("198.51.100.50", 6, 443, 51000) == ("LAN cache", "downloads")


@pytest.mark.parametrize("rules", [[{"category": "gaming"}], [{"name": "x", "category": "piracy"}],
                                   [{"name": "x", "cidr": ["300.1.1.0/24"]}], [{"name": "x", "ports": ["icmp/1"]}]])
def test_broken_rules_are_reported(rules, monkeypatch):
    monkeypatch.setenv("FLOWS_SERVICES", json.dumps(rules))
    found, error = classify.load_rules()
    assert error and found == compile_rules(classify.BUILTIN)


# ── aggregating ───────────────────────────────────────────────────────────────────────────
@pytest.fixture
def agg():
    a = Aggregator(Classifier())
    a.set_seats(SEATS, AREAS)
    return a


def test_only_hall_traffic_counts_and_mixes_add_up(agg):
    agg.add([STEAM, rec("192.0.2.11", "203.0.113.9", 51000, 443, proto=6, size=2_000_000),
             rec("203.0.113.1", "203.0.113.2", 1, 2, size=10**9)], now=NOW, exporter="198.51.100.1")
    snap = agg.snapshot(now=NOW + 1)
    assert snap["mix_hour"] == {"gaming": 5_000_000, "web": 2_000_000} == snap["mix_day"]
    assert snap["areas"] == [{"area": "A", "bytes": 7_000_000, "mix": {"gaming": 5_000_000, "web": 2_000_000}}]
    assert snap["flows"] == 2 and snap["exporters"][0]["address"] == "198.51.100.1"


def test_a_service_is_only_named_once_enough_seats_used_it(agg, monkeypatch):
    monkeypatch.setenv("FLOWS_MIN_SEATS", "3")
    flows = [rec("203.0.113.30", f"192.0.2.{10 + i}", 27015, 50000) for i in range(3)]
    flows.append(rec("203.0.113.40", "192.0.2.10", 1935, 50001, proto=6, size=777))   # one seat only
    agg.add(flows, now=NOW)
    snap = agg.snapshot(now=NOW + 1)
    assert [(s["name"], s["seats"]) for s in snap["services"]] == [("Steam", 3)]
    assert snap["other_services"] == 777
    assert "203.0.113" not in json.dumps(snap)   # no remote addresses anywhere


def test_a_service_has_down_up_a_trend_and_blocks_of_enough_seats(agg, monkeypatch):
    monkeypatch.setenv("FLOWS_MIN_SEATS", "3")
    agg.set_seats(SEATS, {**AREAS, "A-6": "B", "A-7": "B"})
    hour = NOW // 3600 * 3600
    down = [rec("203.0.113.30", f"192.0.2.{10 + i}", 27015, 50000, size=1000) for i in range(7)]
    up = rec("192.0.2.10", "203.0.113.30", 50000, 27015, size=300)
    agg.add(down, now=hour + 10)
    agg.add([up], now=hour + 3600 + 10)
    [steam] = agg.snapshot(now=hour + 3600 + 20)["services"]
    assert (steam["down"], steam["up"], steam["seats"]) == (7000, 300, 7)
    assert steam["trend"] == {str(hour): 7000, str(hour + 3600): 300}
    # Block B had two of its seats on Steam: under the floor of three, so it isn't named.
    assert steam["areas"] == {"A": 5300}


def test_per_seat_is_volume_and_mix_only(agg):
    agg.add([STEAM, rec("192.0.2.10", "203.0.113.9", 51000, 443, proto=6, size=1000)], now=NOW)
    [seat] = agg.snapshot(now=NOW + 1)["seats"]
    assert seat == {"seat": "A-1", "area": "A", "bytes": 5_001_000, "mix": {"gaming": 5_000_000, "web": 1000}}


def test_windows_age_out(agg):
    agg.add([STEAM], now=NOW)
    snap = agg.snapshot(now=NOW + 2 * 3600)
    assert snap["mix_hour"] == {} and snap["mix_day"] == {"gaming": 5_000_000}
    assert agg.snapshot(now=NOW + 26 * 3600)["mix_day"] == {}


def test_closed_hours_keep_no_seats(agg, monkeypatch):
    monkeypatch.setenv("FLOWS_MIN_SEATS", "2")
    agg.add([STEAM, rec("203.0.113.30", "192.0.2.11", 27015, 50000)], now=NOW)
    agg.tick(now=NOW + 3600)
    [(start, hour)] = agg.take_closed_hours()
    assert start == NOW // 3600 * 3600
    assert hour["services"] == {"Steam": {"bytes": 5_001_000, "down": 5_001_000, "up": 0, "category": "gaming",
                                          "seats": 2}}
    assert "A-1" not in json.dumps(hour) and "192.0.2" not in json.dumps(hour)


def test_per_seat_numbers_go_after_the_retention(agg, monkeypatch):
    monkeypatch.setenv("FLOWS_RETENTION_DAYS", "1")
    agg.add([STEAM], now=NOW)
    agg.tick(now=NOW + 2 * 86400)
    assert agg.hours == {}


# ── anomalies ─────────────────────────────────────────────────────────────────────────────
def test_p2p_flood(agg, monkeypatch):
    monkeypatch.setenv("FLOWS_P2P_PEERS", "50")
    agg.add([rec("192.0.2.13", f"198.18.0.{p}", 6881, 30000 + p) for p in range(60)], now=NOW)
    agg.tick(now=NOW + 60)
    [a] = agg.snapshot(now=NOW + 61)["anomalies"]
    assert a["kind"] == "p2p" and a["seat"] == "A-4" and "60 peers" in a["detail"]
    agg.tick(now=NOW + 60 + 11 * 60)
    assert agg.snapshot(now=NOW + 60 + 11 * 60)["anomalies"] == []   # gone once it stops


def test_rogue_dhcp_and_dns(agg):
    agg.add([rec("192.0.2.17", "255.255.255.255", 67, 68), rec("192.0.2.12", "192.0.2.15", 53, 50000)], now=NOW)
    agg.tick(now=NOW + 60)
    kinds = sorted((a["kind"], a["seat"]) for a in agg.snapshot(now=NOW + 61)["anomalies"])
    assert kinds == [("rogue-dhcp", "A-8"), ("rogue-dns", "A-3")]


def test_ddos_like_burst(agg, monkeypatch):
    monkeypatch.setenv("FLOWS_BURST_PPS", "1000")
    agg.add([rec(f"192.0.2.{10 + i}", "203.0.113.99", 40000, 80, packets=30_000) for i in range(4)], now=NOW)
    agg.tick(now=NOW + 60)
    anomalies = agg.snapshot(now=NOW + 61)["anomalies"]
    assert any(a["kind"] == "burst" and "203.0.113.99" in a["title"] and "4 seats" in a["detail"] for a in anomalies)


# ── collector and storage ─────────────────────────────────────────────────────────────────
def test_collector_reads_writes_raw_and_publishes(tmp_path, monkeypatch, app_module):
    col = Collector(Aggregator(Classifier()), store.RawStore(str(tmp_path)), log=lambda *_: None)
    col.publish = store.publish   # what Floorbit does with the summary the agent sends
    assert col.receive(v5([STEAM]), "198.51.100.1", now=NOW) == 1
    assert col.receive(b"nonsense", "198.51.100.1", now=NOW) == 0 and col.errors == 1
    col.housekeeping(now=NOW + 1, refresh_seats=lambda: (SEATS, AREAS))   # seats come after the first packet
    col.receive(v5([STEAM]), "198.51.100.1", now=NOW + 2)
    col._next["publish"] = col._next["raw"] = 0   # both are due (raw is written every RAW_EVERY s)
    col.housekeeping(now=NOW + 3, refresh_seats=lambda: (SEATS, AREAS))
    snap = store.latest()
    assert snap["mix_hour"] == {"gaming": 5_000_000} and snap["raw"]["files"] == 1 and snap["errors"] == 1
    [name] = os.listdir(tmp_path / "raw")
    with gzip.open(tmp_path / "raw" / name, "rt") as f:
        assert len(f.readlines()) == 2   # raw keeps every flow, also the one before the seats were known


def test_raw_files_go_after_the_retention(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWS_RETENTION_DAYS", "7")
    raw = store.RawStore(str(tmp_path))
    raw.write([STEAM], now=NOW - 8 * 86400)
    raw.write([STEAM], now=NOW - 86400)
    assert raw.usage()["files"] == 2
    assert raw.prune(now=NOW) == 1 and raw.usage()["files"] == 1



def test_raw_files_keep_to_a_size_cap_oldest_first(tmp_path, monkeypatch):
    # A week of a busy hall's flows is over 50 GB, on the agent's small disk.
    monkeypatch.setenv("FLOWS_RAW_MAX_MB", "1")
    raw = store.RawStore(str(tmp_path))
    for hour in range(4):
        raw.write([STEAM], now=NOW - (4 - hour) * 3600)
    names = sorted(os.listdir(tmp_path / "raw"))
    for name in names:
        (tmp_path / "raw" / name).write_bytes(os.urandom(400_000))
    assert raw.prune(now=NOW) == 2
    assert sorted(os.listdir(tmp_path / "raw")) == names[2:]
    (tmp_path / "raw" / names[3]).write_bytes(os.urandom(1_500_000))   # the hour being written, alone over
    raw.prune(now=NOW)
    assert sorted(os.listdir(tmp_path / "raw")) == names[3:]

def test_no_raw_flows_when_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOWS_KEEP_RAW", "false")
    raw = store.RawStore(str(tmp_path))
    raw.write([STEAM], now=NOW)
    assert raw.usage()["files"] == 0


# ── API ───────────────────────────────────────────────────────────────────────────────────
def test_api_without_a_collector(client):
    assert client.get("/api/flows").get_json()["collector"] is False


def test_api_hides_seats_without_seats_view(client, kiosk_client, anon_client, monkeypatch, agg):
    agg.add([STEAM, rec("192.0.2.17", "255.255.255.255", 67, 68)], now=NOW)
    agg.tick(now=NOW + 60)
    store.publish(agg.snapshot(now=NOW + 61))
    full = client.get("/api/flows").get_json()
    assert full["collector"] and full["seats"][0]["seat"] == "A-1" and full["anomalies"][0]["seat"] == "A-8"
    assert anon_client.get("/api/flows").status_code == 401
    public = kiosk_client.get("/api/flows").get_json()
    assert public["seats"] is None and public["mix_hour"] == full["mix_hour"]
    assert "A-8" not in json.dumps(public) and "A-1" not in json.dumps(public["anomalies"])
    assert public["anomalies"][0]["title"] == "DHCP server at a seat"


def test_api_anomalies_in_german(client, monkeypatch, agg):
    agg.add([STEAM, rec("192.0.2.17", "255.255.255.255", 67, 68)], now=NOW)
    agg.tick(now=NOW + 60)
    store.publish(agg.snapshot(now=NOW + 61))
    [a] = client.get("/api/flows", headers={"Accept-Language": "de-CH"}).get_json()["anomalies"]
    assert (a["title"], a["detail"]) == ("Platz A-8 antwortet auf DHCP", "ein DHCP-Server, der nicht unserer ist")
    # the German is per answer: the next English reader gets English
    assert client.get("/api/flows").get_json()["anomalies"][0]["title"] == "Seat A-8 answers DHCP"


def test_demo_flows_show_every_kind():
    from floorbit.flows.demo import DemoFlows
    demo = DemoFlows()
    demo.backfill(now=NOW, minutes=5)
    snap = demo.snapshot()
    assert {"gaming", "streaming", "downloads", "updates", "web"} <= set(snap["mix_day"])
    assert any(a["kind"] == "p2p" and a["seat"] == "D-5" for a in snap["anomalies"])


def test_settings_have_floors(monkeypatch):
    monkeypatch.setenv("FLOWS_MIN_SEATS", "1")
    assert aggregate.settings()["min_seats"] == 2
