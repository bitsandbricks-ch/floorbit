"""IP and MAC history (floorbit/endpoints.py): rows per machine and port, search, port and seat."""
import pytest
from test_telemetry import mac_tables, snmp_poll

from floorbit import endpoints
from floorbit.telemetry import clients, state

NOW = 1_800_000_000


@pytest.fixture
def db(tmp_path):
    from floorbit import database
    sql = database.Sql(f"sqlite:///{tmp_path / 'ep.db'}", str(tmp_path))
    yield sql
    sql.close()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    state.state.reset()
    monkeypatch.setattr(endpoints, "_seats", lambda: {("sw-a-01", "gi1/0/1"): "A-1"})
    endpoints.reset()
    yield
    endpoints.reset()


def test_the_telemetry_picture_gives_each_machine_its_access_port():
    state.state.apply_text(snmp_poll(NOW, 0), NOW)
    state.state.apply_text(mac_tables(NOW), NOW)
    rows = clients.sightings(state.state)
    seat_row = next(r for r in rows if r["mac"] == "02:00:00:00:00:07")
    # On the access port, not the core's downlink (a CDP neighbour) nor the uplink.
    assert seat_row == {"mac": "02:00:00:00:00:07", "ip": "192.0.2.40", "device": "sw-a-01", "port": "Gi1/0/1",
                        "vlan": "10"}


def test_rows_stay_open_while_seen_and_split_on_a_move(db):
    h = endpoints.History(db)
    seen = {"mac": "02:00:00:00:00:07", "ip": "192.0.2.40", "device": "sw-a-01", "port": "Gi1/0/1", "vlan": "10"}
    h.record([seen], NOW)
    h.record([seen], NOW + 60)
    h.record([{**seen, "port": "Gi1/0/2"}], NOW + 120)              # moved one port over
    h.record([seen], NOW + 120 + endpoints.GAP + 60)                 # back, after a while away
    rows = h.search("02:00:00:00:00:07")
    assert [(r["port"], r["seat"]) for r in rows] == [("Gi1/0/1", "A-1"), ("Gi1/0/2", None), ("Gi1/0/1", "A-1")]
    assert rows[2]["first_seen"] == NOW and rows[2]["last_seen"] == NOW + 60
    # Any notation of a MAC, a part of it, or the start of an IP.
    assert len(h.search("0200.0000.0007")) == 3 and len(h.search("00:07")) == 3 and len(h.search("192.0.2")) == 3
    assert h.search("198.51") == [] and h.search("a") == []
    assert len(h.at_port("SW-A-01", "GigabitEthernet1/0/1")) == 2
    assert len(h.at_seat("A-1")) == 2
    # A restart picks the open row up again instead of starting a new one.
    again = endpoints.History(db)
    again.record([seen], NOW + 120 + endpoints.GAP + 120)
    assert len(again.search("192.0.2.40")) == 3


def test_old_rows_are_pruned(db, monkeypatch):
    monkeypatch.setenv("FLOORBIT_ENDPOINT_DAYS", "1")
    h = endpoints.History(db)
    h.record([{"mac": "020000000007", "ip": "", "device": "sw-a-01", "port": "Gi1/0/1"}], NOW)
    h.prune(NOW + 2 * 86400)
    assert h.search("020000000007") == []


def test_without_a_database_the_last_day_stays_in_memory():
    h = endpoints.History(None)
    h.record([{"mac": "02:00:00:00:00:07", "ip": "192.0.2.40", "device": "sw-a-01", "port": "Gi1/0/1"}], NOW)
    assert h.search("192.0.2.40")[0]["seat"] == "A-1" and h.status()["store"] == "memory"


@pytest.mark.parametrize(("query", "address"), [
    ("192.0.2.4", True), ("10.4.12", True), ("02:00:00", True), ("0200.0000.0007", True), ("2001:db8::1", True),
    ("A-12", False), ("core", False), ("12", False)])
def test_what_counts_as_an_address(query, address):
    assert endpoints.looks_like_address(query) is address


@pytest.fixture
def viewer_client(app_module):
    app_module.app.extensions["auth"].users.add("ana", "ana-password-1", role="viewer")
    c = app_module.app.test_client()
    c.post("/login", data={"username": "ana", "password": "ana-password-1"})
    return c


def test_search_go_to_and_the_agent(client, viewer_client):
    endpoints.history().record([{"mac": "02:00:00:00:00:07", "ip": "192.0.2.40", "device": "sw-a-01",
                                 "port": "Gi1/0/1"}])
    got = client.get("/api/endpoints?q=192.0.2.40").get_json()
    assert got["rows"][0]["mac"] == "02:00:00:00:00:07" and got["rows"][0]["seat"] == "A-1"
    assert client.get("/api/endpoints?seat=A-1").get_json()["rows"]
    assert client.get("/api/endpoints?device=sw-a-01&port=Gi1/0/1").get_json()["rows"]
    places = client.get("/api/pages/find?q=192.0.2.40").get_json()["places"]
    assert {"kind": "endpoint", "name": "192.0.2.40 · A-1", "href": "/endpoints?q=192.0.2.40"} in places
    # Machines at the seats are for seats.view only.
    assert viewer_client.get("/api/endpoints?q=192.0.2.40").status_code == 403
    places = viewer_client.get("/api/pages/find?q=192.0.2.40").get_json()["places"]
    assert not any(p["kind"] == "endpoint" for p in places)


def test_the_agent_sends_where_it_saw_each_machine(client, anon_client, tmp_path):
    import importlib

    from test_telemetry import AgentCtx

    from tests.test_agent import enrol
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    ctx = AgentCtx("telemetry", {"targets": []}, {"sends": {"endpoints": {"privacy": "device"}}},
                   state_dir=str(tmp_path))
    part = agent.AgentPlugin(ctx)
    part.state = state.state
    state.state.apply_text(snmp_poll(NOW, 0), NOW)
    state.state.apply_text(mac_tables(NOW), NOW)
    part.send_endpoints(NOW)
    kind, payload = ctx.sent[-1]
    assert kind == "endpoints" and {"mac": "02:00:00:00:00:07", "ip": "192.0.2.40", "device": "sw-a-01",
                                    "port": "Gi1/0/1", "vlan": "10"} in payload["rows"]
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/telemetry", json={"enabled": True})
    got = anon_client.post("/api/agent/v1/plugins/telemetry/endpoints", json={"payload": payload},
                           headers={"Floorbit-Agent-Key": key})
    assert got.status_code == 200 and got.get_json()["taken"] >= 1
    assert client.get("/api/endpoints?q=02:00:00:00:00:07").get_json()["rows"][0]["seat"] == "A-1"
