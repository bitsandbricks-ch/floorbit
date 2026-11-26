"""The seat panel's traffic (#1481, B): a seat's top applications and networks' owners, read on the
agent from its raw flows, behind seats.view and audited."""
import pytest

from floorbit.blueprints import flow_lookup as bp_mod
from floorbit.flows import lookup
from floorbit.flows.classify import Classifier, compile_rules
from tests.test_flow_lookup import HOUR, OWNERS, SEAT, raw  # noqa: F401  # raw is a fixture
from tests.test_ports import audit_lines, sign_in


def test_the_summary_counts_applications_categories_and_owners_never_addresses(raw):  # noqa: F811
    got = lookup.summary(raw, {"sources": [SEAT], "since": HOUR, "until": HOUR + 3600},
                         classify=Classifier(compile_rules([
                             {"name": "BitTorrent", "category": "downloads", "ports": ["udp/6881-6889"]},
                             {"name": "Web", "category": "web", "ports": ["tcp/443"]}])),
                         owner_of=OWNERS.get)
    assert got["bytes"] == 79_009_000                       # the other seat's flow doesn't count
    assert got["categories"] == {"downloads": 79_000_000, "web": 9_000}
    assert got["applications"] == [{"name": "BitTorrent", "category": "downloads", "bytes": 79_000_000},
                                   {"name": "Web", "category": "web", "bytes": 9_000}]
    assert got["owners"] == [{"asn": 64496, "name": "Example Transit", "bytes": 48_000_000}]
    assert "198.51.100.88" not in str(got) and "203.0.113.17" not in str(got)


def test_the_summary_needs_a_seat(raw):  # noqa: F811
    with pytest.raises(lookup.QueryError):
        lookup.summary(raw, {"ports": "udp/6881"})


ANSWER = {"bytes": 79_000_000, "categories": {"downloads": 79_000_000}, "stopped": False,
          "applications": [{"name": "BitTorrent", "category": "downloads", "bytes": 79_000_000}],
          "owners": [{"asn": 64496, "name": "Example Transit", "bytes": 48_000_000}]}


@pytest.fixture
def agents(monkeypatch):
    asked = []

    def ask(spec, way, op, args=None, agent=None):
        asked.append((op, args))
        return [{"agent": "a1", "name": "Hall A", "result": ANSWER},
                {"agent": "a2", "name": "Hall B", "result": ANSWER},
                {"agent": "a3", "name": "Hall C", "error": "timed out"}]
    monkeypatch.setattr(bp_mod.agent_plugins, "ask", ask)
    monkeypatch.setattr(bp_mod, "seat_maps", lambda: ({SEAT: "D-5"}, {"D-5": "D"}))
    return asked


def test_the_seat_panel_asks_the_agents_and_audits_the_look(app_module, client, agents):
    r = client.get("/api/traffic/seat/d-5")
    assert r.status_code == 200
    body = r.get_json()
    assert body["bytes"] == 158_000_000 and body["hours"] == 24
    assert body["applications"] == [{"name": "BitTorrent", "category": "downloads", "bytes": 158_000_000}]
    assert body["owners"][0] == {"asn": 64496, "name": "Example Transit", "bytes": 96_000_000}
    assert body["agents"][2] == {"name": "Hall C", "error": "timed out"}
    (op, args), = agents
    assert op == "seat_summary" and args["sources"] == [SEAT] and args["until"] - args["since"] == 86400
    entry = audit_lines()[-1]
    assert entry["action"] == "Looked at a seat's traffic" and entry["target"] == "seat d-5"


def test_an_unknown_seat_asks_nobody(app_module, client, agents):
    assert client.get("/api/traffic/seat/Z-9").status_code == 404
    assert agents == []


def test_only_seats_view_may_look(app_module, agents):
    viewer = sign_in(app_module, "watcher", "viewer")
    assert viewer.get("/api/traffic/seat/D-5").status_code == 403
    assert agents == []
