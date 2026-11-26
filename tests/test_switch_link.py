"""Switch SSH over the local agent (floorbit/switch_link.py): with an agent enrolled, port actions,
commands and the terminal are opened on the event network, never from this server. The pinned host
keys stay here, and the login only goes along for the one call.

The "agent" is a thread on the Flask test client that runs the SSH plugin the way the agent does
(floorbit-agent's switches.py), against the fake switch of tests/test_ports.py."""
import json
import threading
import time

import pytest

from floorbit import agent_link, ports
from tests.test_agent import clean_tunnel, enrol, head  # noqa: F401  # the fixture resets the tunnel
from tests.test_ports import FakeSwitch, bounce, ssh, switch  # noqa: F401  # fixtures


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


@pytest.fixture(autouse=True)
def fresh():
    for state in (ports._last, ports._failures, ports._busy):
        state.clear()


class FakeAgent:
    """Takes calls like the agent and answers switch calls with the SSH plugin, as switches.py does.
    It runs in this process, so its tests ask for ``lan_here`` (the agent may reach the switches)."""

    def __init__(self, app_module, registry, key):
        self.registry, self.key, self.seen = registry, key, []
        self.client = app_module.app.test_client()
        self.stop = threading.Event()
        # Set after the first poll. The old wait gave up silently after 5 s, so on a loaded CI
        # runner a test could post before the agent was connected and get "not connected" (#1567).
        self.polled = threading.Event()
        self.shells = {}
        self.thread = threading.Thread(target=self.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        assert self.polled.wait(15), "the fake agent never got its first poll answered"
        assert agent_link.tunnel.connected()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(5)

    def run(self):
        while not self.stop.is_set():
            calls = self.client.get("/api/agent/v1/calls?wait=0.3", headers=head(self.key)).get_json()["calls"]
            self.polled.set()
            for c in calls:
                threading.Thread(target=self.answer, args=(c,), daemon=True).start()

    def answer(self, c):
        self.seen.append((c["method"], json.loads(json.dumps(c["args"]))))
        try:
            result = self.run_one(c["method"], c["args"])
            out = {"id": c["id"], "ok": True, "result": result}
        except Exception as exc:  # noqa: BLE001  # the hosted side gets the message
            out = {"id": c["id"], "ok": False, "error": str(exc)}
        self.client.post("/api/agent/v1/answers", json={"answers": [out]}, headers=head(self.key))

    def run_one(self, method, args):
        spec = self.registry.specs.get("ssh-ports")
        if method == "switch_call":
            _pid, name, target = args
            result = self.registry.call(spec, name, target)
            return {"result": result, "pinned": target.get("pinned_new")}
        if method == "shell_open":
            target = args[1]
            shell = self.registry.call(spec, "open_shell", target)
            self.shells["s1"] = {"shell": shell, "out": ""}
            return {"id": "s1", "pinned": target.get("pinned_new")}
        if method == "shell_io":
            sid, data, _size, after, wait = args
            s = self.shells[sid]
            if data:
                s["shell"].send(data)
            deadline = time.time() + min(wait, 0.5)
            while True:
                got = s["shell"].recv()
                s["out"] += got or ""
                if len(s["out"]) > after or time.time() > deadline:
                    break
                time.sleep(0.02)
            return {"data": s["out"][after:], "next": len(s["out"]), "closed": False}
        if method == "shell_close":
            self.shells.pop(args[0], None)
            return True
        raise RuntimeError(f"{method}: not in this test")


def test_a_bounce_runs_on_the_agent_and_the_host_key_is_pinned_here(lan_here, app_module, client, ssh, registry):  # noqa: F811  # ssh: the fixture from tests/test_ports.py
    key = enrol(client)["key"]
    with FakeAgent(app_module, registry, key) as agent:
        resp = bounce(client, username="kim", password=FakeSwitch.password)
        assert resp.status_code == 200, resp.get_json()
        assert FakeSwitch.last.sent[:4] == ["configure terminal", "interface Gi1/0/3", "shutdown", "end"]
        _method, args = next(s for s in agent.seen if s[0] == "switch_call")
        assert args[:2] == ["ssh-ports", "bounce_port"]
        assert args[2]["pinned"] is None and args[2]["login"] == {"username": "kim",
                                                                  "password": FakeSwitch.password}
        assert set(args[2]) >= {"switch", "host", "port"} and "stored" not in args[2]["login"]
        # Pinned here, from the agent's answer, so every agent checks the switch against the same key.
        assert list(registry.state_of("ssh-ports")["hosts"]) == ["198.51.100.4"]

        ports._last.clear()
        assert bounce(client, username="kim", password=FakeSwitch.password).status_code == 200
        assert [a for m, a in agent.seen if m == "switch_call"][-1][2]["pinned"].startswith("ssh-")

        FakeSwitch.key = b"key-two"
        ports._last.clear()
        resp = bounce(client, username="kim", password=FakeSwitch.password)
        assert resp.status_code == 502 and "changed" in resp.get_json()["error"]
    kept = json.dumps(registry.state_of("ssh-ports"))
    assert FakeSwitch.password not in kept


def test_without_a_connected_agent_nothing_is_opened_from_here(app_module, client, ssh, monkeypatch):  # noqa: F811  # ssh: the fixture from tests/test_ports.py
    enrol(client)
    opened = []
    monkeypatch.setattr(FakeSwitch, "connect", lambda *a, **k: opened.append(a))
    resp = bounce(client, username="kim", password=FakeSwitch.password)
    assert resp.status_code == 502 and "agent" in resp.get_json()["error"]
    assert opened == []


def test_switch_commands_go_through_the_agent(lan_here, app_module, client, ssh, registry):  # noqa: F811  # ssh: the fixture from tests/test_ports.py
    key = enrol(client)["key"]
    with FakeAgent(app_module, registry, key) as agent:
        resp = client.post("/api/commands/run", json={"switches": ["sw-a-01"], "template": "version",
                                                      "username": "kim", "password": FakeSwitch.password})
        assert resp.status_code == 200, resp.get_json()
        calls = [a for m, a in agent.seen if m == "switch_call"]
        assert calls and calls[0][1] == "send_commands", resp.get_json()["results"]


def test_the_terminal_is_held_open_by_the_agent(lan_here, app_module, client, ssh, registry, monkeypatch):  # noqa: F811  # ssh: the fixture from tests/test_ports.py
    from tests.test_ports import FakeShell
    # What paramiko's channel has beyond the fake one of tests/test_ports.py.
    monkeypatch.setattr(FakeShell, "closed", False, raising=False)
    monkeypatch.setattr(FakeShell, "exit_status_ready", lambda self: False, raising=False)
    monkeypatch.setattr(FakeShell, "sendall", lambda self, data: self.send(data.decode()), raising=False)
    key = enrol(client)["key"]
    with FakeAgent(app_module, registry, key) as agent:
        resp = client.post("/api/terminal", json={"switch": "sw-a-01", "username": "kim",
                                                  "password": FakeSwitch.password})
        assert resp.status_code in (200, 201), resp.get_json()
        sid = resp.get_json()["id"]
        assert client.post(f"/api/terminal/{sid}/input", json={"data": "show clock\r"}).status_code == 200
        deadline = time.time() + 5
        while "show clock" not in FakeSwitch.last.sent and time.time() < deadline:
            time.sleep(0.05)
        assert "show clock" in FakeSwitch.last.sent
        assert len(agent.shells) == 1     # the shell lives on the agent, not here
        assert client.delete(f"/api/terminal/{sid}").status_code == 200
        deadline = time.time() + 5
        while not any(m == "shell_close" for m, _ in agent.seen) and time.time() < deadline:
            time.sleep(0.05)
        methods = {m for m, _ in agent.seen}
        assert {"shell_open", "shell_io", "shell_close"} <= methods
