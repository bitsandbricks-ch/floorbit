"""Shelly and Home Assistant meters as agent plugins: read in the hall, handed to Electrics by
meter id. Only localhost."""
import http.server
import importlib.util
import json
import pathlib
import threading
import time

import pytest
from test_agent import enrol, head

from floorbit import power
from floorbit.plugins.agent import MemoryContext

ROOT = pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins"


def _agent_module(plugin):
    spec = importlib.util.spec_from_file_location(f"{plugin}_agent", ROOT / plugin / "agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fake(http.server.BaseHTTPRequestHandler):
    routes = {}  # noqa: RUF012  # set per test

    def do_GET(self):
        status, body = self.routes.get(self.path, (404, {}))
        if status == 401 and self.headers.get("Authorization") == "Bearer good-token":
            status, body = self.routes.get("ok:" + self.path, (404, {}))
        data = json.dumps(body).encode()
        self.send_response(status)
        if status == 401:
            self.send_header("WWW-Authenticate", 'Basic realm="x"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Fake.routes = {}
    yield f"127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_shelly_lines_and_both_generations():
    m = _agent_module("shelly")
    assert m.parse_devices("db1-1 = 192.0.2.50\nbad line\ndb1-2=http://192.0.2.51/ em:0") == [
        ("db1-1", "192.0.2.50", None), ("db1-2", "192.0.2.51", "em:0")]
    status = {"switch:0": {"apower": 100.5}, "switch:1": {"apower": 20}, "em:0": {"total_act_power": 3000},
              "sys": {"apower": 9}}
    assert m.watts_from_rpc(status) == 3120.5 and m.watts_from_rpc(status, "switch:1") == 20
    assert m.watts_from_rpc({"sys": {}}) is None
    assert m.watts_from_status({"meters": [{"power": 40}, {"power": 2}]}) == 42
    assert m.watts_from_status({"emeters": [{"power": 900}]}, "0") == 900
    assert m.watts_from_status({"meters": []}, "3") is None


def test_shelly_reads_sends_and_stops_trying_a_refused_password(fake):
    m = _agent_module("shelly")
    Fake.routes = {"/rpc/Shelly.GetStatus": (200, {"switch:0": {"apower": 230}}),
                   "/status": (200, {"meters": [{"power": 1}]})}
    settings = {"devices": f"db1-1 = {fake}\ndb1-2 = {fake} switch:3", "password": ""}
    ctx = MemoryContext("shelly", settings, {"sends": {"readings": {"privacy": "device", "latest": True}}})
    plugin = m.AgentPlugin(ctx)
    plugin.devices, plugin.rev = m.parse_devices(settings["devices"]), "r1"
    readings, failed = plugin.tick()
    assert readings == [{"meter": "db1-1", "watts": 230}] and "no power reading on switch:3" in failed[0]
    assert ctx.sent[-1] == ("readings", {"readings": [{"meter": "db1-1", "watts": 230}]})
    assert ctx.health_.report()["status"] == "warning"
    # A first-generation Shelly answers /status only.
    Fake.routes = {"/status": (200, {"meters": [{"power": 55}]})}
    assert plugin.tick()[0][0] == {"meter": "db1-1", "watts": 55}
    # A password it refuses: said once, not tried again.
    Fake.routes = {"/rpc/Shelly.GetStatus": (401, {})}
    plugin.tick()
    assert not ctx.may_login(fake, "shelly", "r1") and ctx.health_.report()["status"] == "error"
    assert any("refused the password" in e["error"] for e in ctx.health_.report()["errors"])
    Fake.routes = {"/rpc/Shelly.GetStatus": (200, {"switch:0": {"apower": 1}})}
    assert plugin.tick()[0] == []                       # still blocked
    plugin.rev = "r2"                                   # the password was changed
    assert plugin.tick()[0][0]["watts"] == 1


def test_the_hosted_part_hands_readings_to_electrics(client, anon_client):
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/shelly", json={"enabled": True})
    try:
        res = anon_client.post("/api/agent/v1/plugins/shelly/readings", headers=head(key),
                               json={"payload": {"readings": [{"meter": "db1-1", "watts": 2300},
                                                              {"meter": "bad meter!", "watts": 5}]}})
        assert res.status_code == 200 and res.get_json() == {"kept": 1}
        assert power.agent_readings("shelly") == [{"meter": "db1-1", "watts": 2300}]
        assert power.agent_readings("shelly", now=time.time() + power.AGENT_READING_AGE + 1) == []
    finally:
        client.put("/api/settings/plugins/shelly", json={"enabled": False})


def test_home_assistant_units_and_lines():
    m = _agent_module("home-assistant")
    assert m.parse_sensors("db1-1 = sensor.a\nnope\ndb1-2=sensor.b") == [("db1-1", "sensor.a"), ("db1-2", "sensor.b")]
    unit = lambda u, v: {"state": v, "attributes": {"unit_of_measurement": u}}  # noqa: E731
    assert m.reading(unit("W", "120.5")) == {"watts": 120.5} and m.reading(unit("kW", "2.3")) == {"watts": 2300}
    assert m.reading(unit("A", "7")) == {"amps": 7} and m.reading(unit("W", "unavailable")) is None
    assert m.reading(unit("kWh", "5")) is None


def test_home_assistant_reads_and_stops_on_a_refused_token(fake):
    m = _agent_module("home-assistant")
    states = [{"entity_id": "sensor.a", "state": "2.5", "attributes": {"unit_of_measurement": "kW"}},
              {"entity_id": "sensor.b", "state": "unknown", "attributes": {"unit_of_measurement": "W"}}]
    Fake.routes = {"/api/states": (401, {}), "ok:/api/states": (200, states)}
    sensors = "db1-1 = sensor.a\ndb1-2 = sensor.b\nx = sensor.c"
    settings = {"url": f"http://{fake}", "token": "good-token", "sensors": sensors}
    ctx = MemoryContext("home-assistant", settings, {"sends": {"readings": {"privacy": "device", "latest": True}}})
    plugin = m.AgentPlugin(ctx)
    plugin.sensors, plugin.url, plugin.rev = m.parse_sensors(settings["sensors"]), settings["url"], "r1"
    readings, failed = plugin.tick()
    assert readings == [{"meter": "db1-1", "watts": 2500}] and len(failed) == 2 and "not found" in failed[1]
    ctx.settings["token"] = "wrong"
    plugin.tick()
    assert not ctx.may_login(settings["url"], "home-assistant", "r1")
    ctx.settings["token"] = "good-token"
    assert plugin.tick() == ([], ["token refused"])          # not tried again until cleared


def test_shelly_odd_answers_are_no_reading(fake):
    m = _agent_module("shelly")
    for odd in ([], 5, "x", None, {"meters": 5}, {"emeters": "ab"}, {"meters": [{"power": float("nan")}]},
                {"meters": [{"power": True}]}):
        assert m.watts_from_status(odd) is None and m.watts_from_rpc(odd) is None
    assert m.watts_from_rpc({"switch:0": {"apower": float("inf")}}) is None
    assert m.watts_from_status({"meters": [{"power": 1}]}, "-1") is None
    # A device that answers NaN, or a list: a failed meter, not a stopped round.
    Fake.routes = {"/rpc/Shelly.GetStatus": (200, {"switch:0": {"apower": float("nan")}})}
    ctx = MemoryContext("shelly", {}, {"sends": {"readings": {"privacy": "device", "latest": True}}})
    plugin = m.AgentPlugin(ctx)
    plugin.devices, plugin.rev = m.parse_devices(f"db1-1 = {fake}"), "r1"
    assert plugin.tick() == ([], [f"db1-1: {fake} has no power reading"])
    Fake.routes = {"/rpc/Shelly.GetStatus": (200, [])}
    assert plugin.tick()[0] == []


def test_home_assistant_odd_answers_are_no_reading(fake):
    m = _agent_module("home-assistant")
    for odd in ({"state": "nan", "attributes": {"unit_of_measurement": "W"}},
                {"state": "inf", "attributes": {"unit_of_measurement": "W"}},
                {"state": "5", "attributes": ["W"]}, {"state": "5"}, [], None):
        assert m.reading(odd) is None
    settings = {"url": f"http://{fake}", "token": "t", "sensors": "db1-1 = sensor.a"}
    ctx = MemoryContext("home-assistant", settings, {"sends": {"readings": {"privacy": "device", "latest": True}}})
    plugin = m.AgentPlugin(ctx)
    plugin.sensors, plugin.url, plugin.rev = m.parse_sensors(settings["sensors"]), settings["url"], "r1"
    for body in ({"entity_id": "sensor.a"}, 5, [{"entity_id": ["sensor.a"]}, "x"]):
        Fake.routes = {"/api/states": (200, body)}
        assert plugin.tick()[0] == []


@pytest.mark.parametrize("plugin", ["shelly", "home-assistant"])
def test_a_round_that_breaks_does_not_stop_the_readings(plugin, monkeypatch):
    m = _agent_module(plugin)
    ctx = MemoryContext(plugin, {}, {"sends": {}})
    agent = m.AgentPlugin(ctx)
    agent.interval = 0
    rounds = []

    def tick():
        rounds.append(1)
        if len(rounds) == 1:
            raise KeyError("surprise")
        ctx.stopping.set()

    monkeypatch.setattr(agent, "tick", tick)
    agent.loop()
    assert len(rounds) == 2
    assert any("a round failed" in e["error"] for e in ctx.health_.report()["errors"])


def test_a_meter_address_that_is_no_web_server():
    import socket
    m = _agent_module("shelly")
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def answer():
        conn, _addr = server.accept()
        conn.recv(1000)
        conn.sendall(b"SSH-2.0-OpenSSH_9.6\r\n")
        conn.close()
    threading.Thread(target=answer, daemon=True).start()
    ctx = MemoryContext("shelly", {}, {"sends": {}})
    plugin = m.AgentPlugin(ctx)
    plugin.devices, plugin.rev = [("db1-1", f"127.0.0.1:{server.getsockname()[1]}", None)], "r1"
    readings, failed = plugin.tick()
    server.close()
    assert readings == [] and failed[0].startswith("db1-1: ")


def test_odd_agent_readings_keep_only_numbers():
    kept = power.keep_agent_readings("odd-test", [
        {"meter": "db1-1", "amps": 1, "watts": "5"},           # text is left out
        {"meter": "db1-2", "watts": 10 ** 400},                # used to raise OverflowError
        {"meter": "db1-3", "amps": 2, "watts": [1]},
        {"meter": "db1-4", "watts": 230}])
    assert kept == 3
    assert power.agent_readings("odd-test") == [{"meter": "db1-1", "amps": 1}, {"meter": "db1-3", "amps": 2},
                                                {"meter": "db1-4", "watts": 230}]
