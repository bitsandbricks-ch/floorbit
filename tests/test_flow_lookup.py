"""The flow lookup (#1481, C): the agent's search over its raw flows, and the hosted page's
permission, reason and audit entry."""
import gzip
import json
import os
import time

import pytest

from floorbit.blueprints import flow_lookup as bp_mod
from floorbit.flows import lookup
from floorbit.flows.classify import Classifier, compile_rules
from tests.test_ports import audit_lines, sign_in

HOUR = 1_800_000_000 - 1_800_000_000 % 3600
SEAT = "192.0.2.45"
OWNERS = {"203.0.113.17": (64496, "Example Transit")}


def _write(folder, start, rows):
    os.makedirs(folder, exist_ok=True)
    name = time.strftime("%Y-%m-%d-%H", time.gmtime(start)) + ".jsonl.gz"
    with gzip.open(os.path.join(folder, name), "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


@pytest.fixture
def raw(tmp_path):
    folder = str(tmp_path / "raw")
    _write(folder, HOUR, [
        [HOUR + 60, SEAT, "203.0.113.17", 17, 6881, 6881, 48_000_000, 36_000, 3],
        [HOUR + 120, "198.51.100.88", SEAT, 17, 6881, 6881, 31_000_000, 24_000, 2],
        [HOUR + 180, SEAT, "198.51.100.7", 6, 50000, 443, 9_000, 20, 1],
        [HOUR + 240, "192.0.2.46", "203.0.113.17", 17, 6881, 6881, 5_000, 10, 1],
        "not a row",
    ])
    _write(folder, HOUR - 7 * 86400, [[HOUR - 7 * 86400 + 60, SEAT, "203.0.113.99", 6, 1, 2, 1, 1, 1]])
    return folder


def _search(raw, **args):
    args.setdefault("since", HOUR)
    args.setdefault("until", HOUR + 3600)
    return lookup.search(raw, args, classify=Classifier(compile_rules([
        {"name": "BitTorrent", "category": "downloads", "ports": ["udp/6881-6889"]}])), owner_of=OWNERS.get)


def test_a_seat_finds_its_flows_both_ways_newest_first(raw):
    got = _search(raw, sources=[SEAT], ports="udp/6881-6889")
    assert [r["t"] for r in got["rows"]] == [HOUR + 120, HOUR + 60]
    assert got["total"] == 2 and got["bytes"] == 79_000_000 and got["peers"] == 2
    first, second = got["rows"]
    assert first["protocol"] == "udp" and first["application"] == "BitTorrent"
    assert second["owner"] == {"asn": 64496, "name": "Example Transit"}


def test_owner_address_and_port_filters(raw):
    assert _search(raw, asn=64496)["total"] == 2                       # both seats that reached it
    assert _search(raw, destination=["198.51.100.0/24"])["total"] == 2
    assert _search(raw, sources=[SEAT], ports="443")["total"] == 1
    assert _search(raw, sources=[SEAT], ports="tcp/6881")["total"] == 0
    old = _search(raw, sources=[SEAT], since=HOUR - 7 * 86400, until=HOUR - 7 * 86400 + 3600)
    assert [r["dst"] for r in old["rows"]] == ["203.0.113.99"]


def test_the_minutes_not_on_disk_yet_count_too(raw):
    pending = {(HOUR + 300, SEAT, "203.0.113.5", 17, 6882, 6882): [1000, 2, 1]}
    got = lookup.search(raw, {"sources": [SEAT], "since": HOUR, "until": HOUR + 3600}, pending=pending)
    assert got["rows"][0]["dst"] == "203.0.113.5" and got["total"] == 4


def test_only_the_newest_rows_come_back_but_all_count(raw, monkeypatch):
    got = _search(raw, sources=[SEAT], limit=1)
    assert len(got["rows"]) == 1 and got["rows"][0]["t"] == HOUR + 180 and got["total"] == 3


def test_a_slow_search_stops_and_says_so(raw):
    ticks = iter(range(0, 1000, 20))
    got = lookup.search(raw, {"sources": [SEAT], "since": HOUR - 7 * 86400, "until": HOUR + 3600},
                        clock=lambda: next(ticks))
    assert got["stopped"] is True


@pytest.mark.parametrize("args", [
    {},                                                    # the whole hall
    {"sources": ["not an address"]},
    {"destination": ["300.1.2.3"]},
    {"ports": "icmp/1"},
    {"ports": "443", "since": HOUR, "until": HOUR - 1},
    {"ports": "443", "since": HOUR - 9 * 86400, "until": HOUR},
])
def test_bad_questions_are_refused(raw, args):
    with pytest.raises(lookup.QueryError):
        lookup.search(raw, {"since": HOUR, "until": HOUR + 3600, **args})


# ── the hosted side ───────────────────────────────────────────────────────────

ANSWER = {"rows": [{"t": HOUR + 60, "src": SEAT, "dst": "203.0.113.17", "proto": 17, "protocol": "udp",
                    "sport": 6881, "dport": 6881, "bytes": 48_000_000, "packets": 36_000,
                    "owner": {"asn": 64496, "name": "Example Transit"}, "application": "BitTorrent"}],
          "total": 1, "bytes": 48_000_000, "peers": 1, "stopped": False, "oldest": "2027-01-15-00"}


@pytest.fixture
def agents(monkeypatch):
    asked = []

    def ask(spec, way, op, args=None, agent=None):
        asked.append((spec.id, way, op, args))
        return [{"agent": "a1", "name": "Hall A", "result": ANSWER},
                {"agent": "a2", "name": "Hall B", "error": "timed out"}]
    monkeypatch.setattr(bp_mod.agent_plugins, "ask", ask)
    monkeypatch.setattr(bp_mod, "seat_maps", lambda: ({SEAT: "D-5"}, {"D-5": "D"}))
    return asked


def test_only_traffic_investigate_may_look(app_module, agents):
    tech = sign_in(app_module, "tech1", "tech")
    assert tech.post("/api/traffic/lookup", json={"seat": "D-5", "reason": "incident 42"}).status_code == 403
    assert tech.get("/flow-lookup").status_code == 403
    assert agents == []


def test_a_search_needs_a_reason_and_is_audited_first(app_module, client, agents):
    assert client.post("/api/traffic/lookup", json={"seat": "D-5"}).status_code == 400
    assert client.post("/api/traffic/lookup", json={"seat": "Z-9", "reason": "incident 42"}).status_code == 400
    r = client.post("/api/traffic/lookup", json={"seat": "d-5", "ports": "udp/6881-6889", "window": "1h",
                                                "reason": "P2P flood on the D uplink, incident 42"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["rows"][0]["src_seat"] == "D-5" and body["rows"][0]["agent"] == "Hall A"
    assert body["total"] == 1 and body["agents"][1] == {"name": "Hall B", "total": None, "error": "timed out",
                                                         "oldest": None, "stopped": False}
    (_, _, op, args), = agents
    assert op == "lookup" and args["sources"] == [SEAT] and args["ports"] == "udp/6881-6889"
    entry = audit_lines()[-1]
    assert entry["action"] == "Searched the raw flows" and entry["area"] == "traffic"
    assert entry["reason"] == "P2P flood on the D uplink, incident 42"
    assert entry["target"].startswith("seat d-5, udp/6881-6889, last 1h")


def test_an_owner_by_as_number(app_module, client, agents):
    client.post("/api/traffic/lookup", json={"destination": "AS64496", "reason": "abuse report"})
    assert agents[-1][3]["asn"] == 64496 and "sources" not in agents[-1][3]


def test_the_csv_is_audited_as_an_export(app_module, client, agents):
    r = client.post("/api/traffic/lookup", json={"seat": "D-5", "reason": "incident 42", "csv": True})
    assert r.status_code == 200 and r.mimetype == "text/csv"
    text = r.data.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("time,source,source_seat")
    assert "AS64496 Example Transit" in text and "BitTorrent" in text
    assert audit_lines()[-1]["action"] == "Exported a flow lookup"


def test_the_agent_part_answers_from_its_collector(tmp_path, raw):
    import importlib.util
    import threading

    from floorbit.plugins.agent import MemoryContext
    path = os.path.join(os.path.dirname(bp_mod.__file__), "..", "builtin_plugins", "netflow-relay", "agent.py")
    spec = importlib.util.spec_from_file_location("netflow_relay_agent_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    folder = raw

    class Collector:
        def __init__(self):
            self._lock = threading.Lock()
            self._pending = {}
        raw = type("Raw", (), {"raw": folder})()
        agg = type("Agg", (), {"classify": None})()
        owners = type("Owners", (), {"lookup": staticmethod(OWNERS.get)})()
    plugin = module.AgentPlugin(MemoryContext("netflow-relay"))
    assert "error" in plugin.call_lookup({"sources": [SEAT]})            # no relay: no port set
    plugin.relay = type("Relay", (), {"collector": Collector()})()
    got = plugin.call_lookup({"sources": [SEAT], "since": HOUR, "until": HOUR + 3600})
    assert got["total"] == 3
    assert plugin.call_lookup({}) == {"error": "Name a seat, an address, an owner or a port: not the whole hall"}
