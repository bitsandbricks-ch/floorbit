"""Syslog from the hall as an agent plugin: the agent part listens and spools, the hosted part
hands the lines to the same place relayed syslog always went. Localhost only."""
import socket
import time

from test_agent import enrol, head

from floorbit.plugins.agent import MemoryContext

BLOCK = {"sends": {"lines": {"privacy": "device"}}}


def _agent_part(ctx):
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins" / "syslog-relay" / "agent.py"
    spec = importlib.util.spec_from_file_location("syslog_relay_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentPlugin(ctx)


def test_no_port_means_off():
    ctx = MemoryContext("syslog-relay", {"port": 0}, BLOCK)
    plugin = _agent_part(ctx)
    plugin.start()
    assert ctx.health_.report()["status"] == "off" and plugin.check().startswith("off")


def test_the_agent_part_listens_and_sends_in_chunks(monkeypatch):
    from floorbit_agent import syslog_relay
    monkeypatch.setattr(syslog_relay, "EVERY", 0.05)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    ctx = MemoryContext("syslog-relay", {"port": port, "bind": "127.0.0.1"}, BLOCK)
    plugin = _agent_part(ctx)
    monkeypatch.setitem(type(plugin)._send.__globals__, "CHUNK", 2)
    plugin.start()
    try:
        assert ctx.health_.report()["status"] == "ok"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            for i in range(5):
                s.sendto(f"<189>sw-a-01: %LINK-3-UPDOWN: Interface Gi1/0/{i}, changed state to up".encode(),
                         ("127.0.0.1", port))
        deadline = time.time() + 5
        while time.time() < deadline and sum(len(p["lines"]) for _, p in ctx.sent) < 5:
            time.sleep(0.05)
        lines = [line for _, p in ctx.sent for line in p["lines"]]
        assert len(lines) == 5 and all(len(p["lines"]) <= 2 for _, p in ctx.sent)
        assert lines[0]["from"] == "127.0.0.1" and "Gi1/0/0" in lines[0]["raw"] and lines[0]["id"]
        assert "listening for syslog on UDP" in plugin.check()
    finally:
        ctx.close()


def test_the_hosted_part_takes_the_lines(client, anon_client, app_module):
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/syslog-relay", json={"enabled": True})
    client.put("/api/settings/features", json={"syslog": True})
    receiver = app_module.app.extensions["floorbit_syslog"]
    seen = []
    real = receiver.relay
    receiver.relay = lambda name, lines, dropped=0: seen.append((name, lines, dropped)) or len(lines)
    try:
        line = {"raw": "<189>sw-a-01: hello", "from": "192.0.2.10", "at": time.time(), "id": "abc"}
        res = anon_client.post("/api/agent/v1/plugins/syslog-relay/lines", headers=head(key),
                               json={"payload": {"lines": [line], "dropped": 3}})
        assert res.status_code == 200, res.data
        assert seen == [("Demo LAN 2026", [line], 3)]
    finally:
        receiver.relay = real
        client.put("/api/settings/plugins/syslog-relay", json={"enabled": False})


def test_lines_while_syslog_is_off_are_declined_not_retried(client, anon_client):
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/syslog-relay", json={"enabled": True})
    client.put("/api/settings/features", json={"syslog": False})
    try:
        res = anon_client.post("/api/agent/v1/plugins/syslog-relay/lines", headers=head(key),
                               json={"payload": {"lines": [], "dropped": 0}})
        assert res.status_code == 409 and "turned off" in res.get_json()["error"]
    finally:
        client.put("/api/settings/features", json={"syslog": True})
        client.put("/api/settings/plugins/syslog-relay", json={"enabled": False})
