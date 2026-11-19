"""Why a device sends nothing (docs/telemetry.md, "When a device sends nothing"): Telegraf's
errors read per device and collection type, Telegraf run by the agent itself, and what the hosted
pages get. The Telegraf lines are copied from Telegraf 1.40; no network, no real Telegraf."""
import importlib
import os
import stat
import sys
import time

import pytest

from floorbit.plugins.agent import MemoryContext
from floorbit.telemetry import problems, state, supervisor, telegraf

pytestmark = pytest.mark.usefixtures("lan_here")

REFUSED = ("2026-11-19T08:18:30Z E! [inputs.snmp::sw-a-01] Error in plugin: agent udp://192.0.2.21:161: "
           "performing get on field sysName: error reading from socket: read udp 172.23.0.3:55295->192.0.2.21:161: "
           "recvfrom: connection refused")
GNMI = ('2026-11-19T08:21:05Z E! [inputs.gnmi::core-01] Error in plugin: failed to setup subscription: rpc error: '
        'code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 192.0.2.1:50051: '
        'connect: connection refused"')
VLAN_TIMEOUT = ("2026-11-19T17:19:10Z E! [inputs.snmp::access-a1@vlan1] Error in plugin: agent udp://192.0.2.20:161: "
                "gathering table fb_bridge: performing bulk walk for field ifIndex: request timeout (after 1 retries): "
                "max retries exceeded")
TARGET = {"id": "a1", "name": "sw-a-01", "address": "192.0.2.21", "kind": "switch", "platform": "ios",
          "drivers": ["snmp", "traps"], "snmp_version": "2c", "community": "example", "tables": True}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.delenv("FLOORBIT_TELEGRAF_CONF", raising=False)
    monkeypatch.delenv("FLOORBIT_TELEGRAF", raising=False)
    state.state.reset()
    yield
    state.state.reset()
    state.state.problems = None


def test_telegraf_lines_become_problems_by_device_and_type():
    assert problems.parse_line(REFUSED) == {
        "device": "sw-a-01", "driver": "snmp", "kind": "refused", "address": "192.0.2.21:161",
        "detail": REFUSED.split("Error in plugin: ", 1)[1]}
    found = problems.parse_line(GNMI)
    assert (found["device"], found["driver"], found["kind"]) == ("core-01", "gnmi", "refused")
    assert found["address"] == "192.0.2.1:50051"
    trap = problems.parse_line("2026-11-19T08:00:00Z E! [inputs.snmp_trap::traps] Error in plugin: listen udp :1162: "
                               "bind: address already in use")
    assert trap["device"] == "" and trap["driver"] == "traps" and trap["kind"] == "listen"
    # Information and warnings aren't problems.
    assert problems.parse_line("2026-11-19T08:21:05Z I! [inputs.snmp_trap::traps] Listening on udp://:1162") is None
    assert problems.parse_line("2026-11-19T08:21:05Z W! [agent] The default value will change") is None
    for text, kind in (("request timeout (after 1 retries)", "timeout"), ("unknown username", "auth"),
                       ("wrong digests", "auth"), ("code = Unauthenticated desc = bad login", "auth"),
                       ("dial tcp 192.0.2.9:443: connect: no route to host", "unreachable"),
                       ("tls: failed to verify certificate: x509: certificate signed by unknown authority", "tls"),
                       ("something new", "other")):
        assert problems.kind_of(text) == kind, text
    assert "nothing listens for SNMP on 192.0.2.21:161" in problems.hint(problems.parse_line(REFUSED))


def test_a_problem_goes_once_the_device_sends_or_it_stops_repeating():
    found = problems.Problems(forget_after=100)
    assert found.note(problems.parse_line(REFUSED), now=1000) is True
    assert found.note(problems.parse_line(REFUSED), now=1030) is False      # the same again: no new log line
    assert found.current(1030)[0]["count"] == 2 and found.current(1030)[0]["since"] == 1000
    found.heard({"sw-a-01"}, at=1040)
    assert found.current(1040) == []
    found.note(problems.parse_line(REFUSED), now=2000)
    assert found.current(2050) and found.current(2101) == []
    # The API pollers' errors: each round replaces the last.
    found.sync({"core-01": ("nxapi", "NX-API on core-01 refused the login.")}, now=3000)
    assert [(p["device"], p["kind"]) for p in found.current(3000)] == [("core-01", "auth")]
    found.sync({}, now=3060)
    assert found.current(3060) == []


def test_every_input_is_named_after_its_device():
    import tomllib
    target = {**TARGET, "drivers": ["snmp", "gnmi", "traps"]}
    conf = tomllib.loads(telegraf.render([target], "http://127.0.0.1:8186/write", "t"))
    assert {i["alias"] for i in conf["inputs"]["snmp"]} == {"sw-a-01"}
    assert conf["inputs"]["gnmi"][0]["alias"] == "sw-a-01" and conf["inputs"]["snmp_trap"][0]["alias"] == "traps"


class AgentCtx(MemoryContext):
    tls = False

    def listen_http(self, port, handler, host="0.0.0.0", tls=False):
        self.handler = handler
        return port


def fake_telegraf(tmp_path, lines):
    """A stand-in for the binary: prints Telegraf's lines, then waits like Telegraf does."""
    path = tmp_path / "telegraf"
    path.write_text(f"#!{sys.executable}\nimport sys, time\n"
                    f"for line in {lines!r}:\n    print(line, flush=True)\n"
                    "open(sys.argv[2] + '.started', 'a').write('x')\n"
                    "time.sleep(30)\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def wait_for(check, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if check():
            return True
        time.sleep(0.05)
    return False


def test_the_agent_runs_telegraf_and_says_which_device_fails(tmp_path, monkeypatch):
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    plugin_mod = importlib.import_module("floorbit.builtin_plugins.telemetry.plugin")
    monkeypatch.setenv("FLOORBIT_TELEGRAF_BIN", fake_telegraf(tmp_path, [REFUSED]))
    # A sidecar's config from an older compose file: gone, so that sidecar waits instead of polling.
    (tmp_path / "telegraf.conf").write_text("old")
    ctx = AgentCtx("telemetry", {"targets": [TARGET]}, {"sends": {"series": {"privacy": "device"}}},
                   state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        conf = tmp_path / "own-telegraf" / "telegraf.conf"
        assert "http://127.0.0.1:8186/write" in conf.read_text() and not (tmp_path / "telegraf.conf").exists()
        assert wait_for(lambda: plugin.problems.current())
        plugin.report(time.time())
        report = ctx.health_.report()
        assert report["status"] == "warning" and report["hint"] == "device_problems"
        assert "sw-a-01 (snmp): nothing listens for SNMP on 192.0.2.21:161" in report["message"]
        assert report["metrics"]["devices_failing"] == 1
        # The hosted pages get it with the device, through the monitoring calls.
        row = plugin_mod.Plugin.__new__(plugin_mod.Plugin).devices()
        assert row[0]["hostname"] == "sw-a-01" and row[0]["problems"][0]["kind"] == "refused"
        # The device sends after all: the problem is over.
        token = (tmp_path / "own-telegraf-token").read_text()
        line = b"fb_if,device=sw-a-01,driver=snmp,agent_host=192.0.2.21,ifIndex=1,ifName=Gi1/0/1 ifOperStatus=1i"
        time.sleep(1.1)
        assert ctx.handler("POST", "/write", {"Authorization": f"Token {token}"}, line)[0] == 204
        assert plugin.problems.current() == []
        # The log says Telegraf runs, and every minute what each device gave.
        assert any(x.startswith("Telegraf started (pid ") for x in ctx.lines)
        plugin.log_polls(time.time())
        assert "polls, last minute: 1 points from 1 of 1 devices: sw-a-01 1" in ctx.lines
        assert any("Telegraf posted 1 points from sw-a-01" in x for x in ctx.lines)
        # A wrong token is just refused.
        assert ctx.handler("POST", "/write", {"Authorization": "Token fba_old"}, line)[0] == 401
        # A firewall's own Telegraf pushes with ingest-token, as docs/telemetry.md says: taken.
        push = (tmp_path / "ingest-token").read_text()
        fw = b"pf,host=fw-01.example.org entries=12i"
        assert ctx.handler("POST", "/write", {"Authorization": f"Token {push}"}, fw)[0] == 204
        stream = b"fb_gnmi_if,device=sw-a-01,driver=gnmi,name=Ethernet1/1 state/counters/in-octets=1i"
        assert ctx.handler("POST", "/write", {"Authorization": f"Token {push}"}, stream)[0] == 204
        # A sidecar left from an older compose file polls with Floorbit's config and that token:
        # refused, so nothing is polled twice, and named.
        assert ctx.handler("POST", "/write", {"Authorization": f"Token {push}"}, line)[0] == 401
        plugin.report(time.time())
        assert ctx.health_.report()["hint"] == "telegraf_sidecar_left"
    finally:
        ctx.stopping.set()
        plugin.stop()


def test_telegraf_that_will_not_start_is_an_error_with_its_last_line(tmp_path, monkeypatch):
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    bad = tmp_path / "telegraf"
    bad.write_text(f"#!{sys.executable}\n"
                   "print('2026-11-19T08:00:00Z E! error loading config file: bad toml')\nraise SystemExit(1)\n")
    bad.chmod(bad.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("FLOORBIT_TELEGRAF_BIN", str(bad))
    ctx = AgentCtx("telemetry", {"targets": [TARGET]}, {}, state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        assert wait_for(lambda: plugin.telegraf.exits >= 1)
        plugin.report(time.time())
        report = ctx.health_.report()
        assert report["status"] == "error" and report["hint"] == "telegraf_stopped"
        assert "bad toml" in report["message"]
    finally:
        ctx.stopping.set()
        plugin.stop()


def test_without_the_binary_it_says_to_update_the_image(tmp_path, monkeypatch):
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    monkeypatch.setattr(supervisor, "binary", lambda: None)
    ctx = AgentCtx("telemetry", {"targets": [TARGET]}, {}, state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        assert "http://agent:8186/write" in (tmp_path / "telegraf.conf").read_text()
        plugin.report(time.time())
        report = ctx.health_.report()
        assert report["hint"] == "telegraf_missing" and 'docs/agent.md, "Telegraf"' in report["message"]
    finally:
        ctx.stopping.set()


def test_sidecar_mode_leaves_telegraf_to_the_container(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORBIT_TELEGRAF", "sidecar")
    monkeypatch.setenv("FLOORBIT_TELEGRAF_BIN", fake_telegraf(tmp_path, []))
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    ctx = AgentCtx("telemetry", {"targets": [TARGET]}, {}, state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        assert plugin.telegraf is None and (tmp_path / "telegraf.conf").exists()
    finally:
        ctx.stopping.set()


def test_an_older_page_and_a_bad_hint(client):
    from floorbit.agent_plugins import clean_health
    out = clean_health({"telemetry": {"status": "warning", "message": "m", "hint": "device_problems"},
                        "dns": {"status": "warning", "message": "m", "hint": "<b>x</b>"}})
    assert out["telemetry"]["hint"] == "device_problems" and out["dns"]["hint"] == ""


def test_the_settings_page_shows_each_devices_problem_from_the_agent(client, monkeypatch):
    from floorbit import sources, telemetry

    class Agent:
        def devices(self):
            return [{"hostname": "sw-a-01", "status": 0, "source": "telemetry", "seen": None,
                     "problems": [{"driver": "snmp", "kind": "refused", "address": "192.0.2.21:161", "detail": "x"}]},
                    {"hostname": "sw-a-02", "status": 1, "source": "telemetry", "seen": 1.0, "ports": 53,
                     "macs": 120, "arp": 0, "neighbours": 2},
                    {"hostname": "other", "source": "librenms", "status": 1}]
    from floorbit import agent_plugins
    monkeypatch.setattr(telemetry, "collector_here", lambda: False)
    metrics = {"points": 6720, "series": 124, "sent": 69, "devices_heard": 1, "primary": 1,
               "telegraf_quiet_seconds": 23}
    monkeypatch.setattr(agent_plugins, "health_of", lambda pid: {
        "a1": {"name": "Hall agent", "connected": True, "health": {"status": "ok", "metrics": metrics}}})
    before = sources.use(Agent())
    try:
        body = client.get("/api/telemetry/overview").get_json()
        seen = body["seen"]
    finally:
        sources.use(before)
    assert list(seen) == ["sw-a-01", "sw-a-02"] and seen["sw-a-01"]["problems"][0]["kind"] == "refused"
    # What came in, as the page showed it before the agent collected
    assert seen["sw-a-02"]["ports"] == 53 and seen["sw-a-02"]["macs"] == 120 and "ports" not in seen["sw-a-01"]
    # Is Telegraf posting to the agent, and does the agent forward? From its last report.
    assert body["status"]["devices"] == 1 and body["status"]["points"] == 6720
    agent = body["status"]["agents"][0]
    assert (agent["name"], agent["series"], agent["sent"], agent["quiet"]) == ("Hall agent", 124, 69, 23)
    assert agent["refused"] == 0


def test_the_binary_is_found_only_when_it_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORBIT_TELEGRAF_BIN", str(tmp_path / "nope"))
    assert supervisor.binary() is None
    path = fake_telegraf(tmp_path, [])
    monkeypatch.setenv("FLOORBIT_TELEGRAF_BIN", path)
    assert supervisor.binary() == path and os.access(path, os.X_OK)


def test_test_now_runs_telegraf_once_for_one_device(tmp_path, monkeypatch):
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    fake = tmp_path / "telegraf"
    fake.write_text(
        f"#!{sys.executable}\nimport sys, time\n"
        "if '--test' in sys.argv:\n"
        "    conf = open(sys.argv[sys.argv.index('--config') + 1]).read()\n"
        "    assert 'udp://192.0.2.21:161' in conf and 'snmp_trap' not in conf\n"
        "    print('> fb_if,agent_host=192.0.2.21,device=sw-a-01,ifIndex=1,ifName=Gi1/0/1 ifOperStatus=1i 1')\n"
        "    print('> fb_if,agent_host=192.0.2.21,device=sw-a-01,ifIndex=2,ifName=Gi1/0/2 ifOperStatus=2i 1')\n"
        f"    print({REFUSED!r}, file=sys.stderr)\n"
        "    raise SystemExit(0)\n"
        "time.sleep(30)\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("FLOORBIT_TELEGRAF_BIN", str(fake))
    ctx = AgentCtx("telemetry", {"targets": [TARGET]}, {}, state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        answer = plugin.call_test({"name": "sw-a-01"})
        assert answer["points"] == 2 and answer["summary"]["ports"] == 2
        assert answer["problems"][0]["kind"] == "refused" and answer["ok"] is False
        assert answer["raw"][0].startswith("fb_if,agent_host=192.0.2.21")
        assert state.state.find("sw-a-01").interfaces              # straight into the picture
        assert not list(tmp_path.glob("test-*.conf"))              # the secrets went with it
        assert plugin.call_test({"name": "nope"})["ok"] is False
        # "Raw data": what Telegraf posted, per device.
        token = (tmp_path / "own-telegraf-token").read_text()
        ctx.handler("POST", "/write", {"Authorization": f"Token {token}"},
                    b"fb_sys,device=sw-a-01,agent_host=192.0.2.21 uptime=12i")
        raw = plugin.call_raw({"name": "sw-a-01"})
        assert raw["known"] is True and raw["lines"] == ["fb_sys,device=sw-a-01,agent_host=192.0.2.21 uptime=12i"]
        assert plugin.call_raw({"name": "nope"}) == {"name": "nope", "known": False, "lines": []}
    finally:
        ctx.stopping.set()
        plugin.stop()


def test_test_now_and_raw_go_through_the_agent(client, monkeypatch):
    from floorbit import agent_plugins, telemetry

    asked = []

    def ask(spec, way, op, args=None, agent=None):
        asked.append((way, op, args))
        if op == "raw":
            raw = {"name": args["name"], "known": True, "lines": ["x a=1"]}
            return [{"agent": "a", "name": "Hall 2", "result": raw}]
        return [{"agent": "b", "name": "Other", "result": {"ok": False, "error": "not here"}},
                {"agent": "a", "name": "Hall 2", "result": {"ok": True, "points": 3, "name": args["name"]}}]
    monkeypatch.setattr(agent_plugins, "ask", ask)
    assert client.post("/api/telemetry/test", json={"name": "sw-a-01"}).status_code == 409   # no agent
    monkeypatch.setattr(telemetry, "collector_here", lambda: False)
    tested = client.post("/api/telemetry/test", json={"name": "sw-a-01"}).get_json()
    assert tested["agent"] == "Hall 2" and tested["points"] == 3
    assert client.get("/api/telemetry/raw?name=sw-a-01").get_json()["lines"] == ["x a=1"]
    assert client.post("/api/telemetry/test", json={}).status_code == 400
    assert asked[0] == ("call", "test", {"name": "sw-a-01"})
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert "Tested telemetry from sw-a-01" in actions


def test_the_crew_cannot_test_or_read_raw_lines(anon_client):
    assert anon_client.post("/api/telemetry/test", json={"name": "sw-a-01"}).status_code in (401, 403)
    assert anon_client.get("/api/telemetry/raw?name=sw-a-01").status_code in (401, 403)


def test_test_now_and_silent_devices_are_logged(tmp_path, monkeypatch):
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    monkeypatch.setattr(supervisor, "binary", lambda: None)
    # A device that only sends traps speaks when something happens: a quiet minute is no news.
    traps_only = {**TARGET, "id": "a2", "name": "pdu-01", "drivers": ["traps"]}
    ctx = AgentCtx("telemetry", {"targets": [TARGET, traps_only]}, {}, state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        plugin.call_test({"name": "sw-a-99"})
        assert "Test now: sw-a-99 is not among the devices this agent collects from" in ctx.lines
        result = plugin.call_test({"name": "sw-a-01"})
        assert not result["ok"] and "Test now on sw-a-01 (snmp, traps)" in ctx.lines
        said = ctx.lines[-1]
        assert said.startswith("Test now on sw-a-01: 0 points in ") and said.endswith("(failed)")
        assert "snmp: this agent image has no Telegraf to test with" in said
        plugin.log_polls(time.time())
        assert ctx.lines[-1] == "nothing in the last minute from 1: sw-a-01"
    finally:
        ctx.stopping.set()


def test_a_vlan_that_does_not_answer_is_named_and_does_not_flap():
    found = problems.parse_line(VLAN_TIMEOUT)
    assert found["device"] == "access-a1" and found["vlan"] == 1 and found["table"] == "fb_bridge"
    assert found["kind"] == "timeout"
    hint = problems.hint(found)
    assert "VLAN 1" in hint and "community@1" in hint and "ACL" not in hint and "telemetry_vlans" in hint
    # A walk that times out without a VLAN: not blamed on the login alone.
    walk = problems.parse_line(VLAN_TIMEOUT.replace("access-a1@vlan1", "access-a1"))
    assert "vlan" not in walk and "fb_bridge" in problems.hint(walk)
    # The switch's other polls answer: that doesn't end this VLAN's problem, so it isn't logged anew.
    p = problems.Problems()
    assert p.note(found, now=100)
    p.heard({"access-a1"}, at=130)
    assert not p.note(found, now=160)
    assert [x["vlan"] for x in p.of("access-a1", now=170)] == [1]
    assert p.of("access-a1", now=160 + problems.FORGET_AFTER + 1) == []


def test_one_vlan_that_does_not_answer_is_not_a_failing_device(tmp_path, monkeypatch):
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    line = VLAN_TIMEOUT.replace("access-a1@vlan1", "sw-a-01@vlan1").replace("192.0.2.20", "192.0.2.21")
    monkeypatch.setenv("FLOORBIT_TELEGRAF_BIN", fake_telegraf(tmp_path, [line, REFUSED]))
    ctx = AgentCtx("telemetry", {"targets": [TARGET]}, {"sends": {"series": {"privacy": "device"}}},
                   state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        assert wait_for(lambda: len(plugin.problems.current()) == 2)
        # The device's own problem isn't hidden behind its VLAN's: both are logged.
        assert any("no answer from 192.0.2.21:161 for VLAN 1" in x for x in ctx.lines)
        assert any("nothing listens for SNMP" in x for x in ctx.lines)
        token = (tmp_path / "own-telegraf-token").read_text()
        time.sleep(1.1)
        sent = b"fb_if,device=sw-a-01,driver=snmp,agent_host=192.0.2.21,ifIndex=1,ifName=Gi1/0/1 ifOperStatus=1i"
        assert ctx.handler("POST", "/write", {"Authorization": f"Token {token}"}, sent)[0] == 204
        # It sends: its own problem is over, VLAN 1's is not, and that is no failing device.
        assert [p.get("vlan") for p in plugin.problems.current()] == [1]
        plugin.report(time.time())
        report = ctx.health_.report()
        assert report["hint"] == "device_partial" and "1 of 1 devices answer only in part" in report["message"]
        assert report["metrics"]["devices_failing"] == 0
    finally:
        plugin.stop()


def test_api_poller_errors_keep_the_cause():
    """"ConnectionError" alone reads the same for a closed port, no route and a wrong name."""
    from floorbit.telemetry import pollers
    refused = OSError('HTTPSConnectionPool(...): Failed to establish a new connection: '
                      '[Errno 111] Connection refused"))')
    named = OSError("Failed to resolve 'sw.example.org' ([Errno -2] Name or service not known)")
    assert pollers._why(refused) == "OSError: Connection refused"
    assert problems.kind_of(pollers._why(refused)) == "refused"
    assert problems.kind_of(pollers._why(named)) == "unreachable"
    assert pollers._why(TimeoutError("read timed out")) == "TimeoutError"
