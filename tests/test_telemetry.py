"""Device telemetry without LibreNMS (docs/telemetry.md): line protocol in, the latest picture of
each device, the telemetry monitoring plugin, Telegraf's config, the API pollers and storage.
No network: pollers get a fake requests session, storage a local SQLite file."""
import base64
import gzip
import json
import os
import time

import pytest

from floorbit.plugins.agent import MemoryContext
from floorbit.telemetry import lineproto, pollers, state, storage, telegraf

SW = "device=sw-a-01,address=192.0.2.21,driver=snmp"
CORE = "device=core-01,address=192.0.2.1,driver=snmp"


def key_file(path):
    path.write_bytes(base64.b64encode(os.urandom(32)))
    return str(path)


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "key"))
    monkeypatch.delenv("FLOORBIT_VICTORIAMETRICS_URL", raising=False)
    monkeypatch.delenv("FLOORBIT_VICTORIALOGS_URL", raising=False)
    monkeypatch.setenv("FLOORBIT_TELEGRAF_CONF", str(tmp_path / "telegraf" / "telegraf.conf"))
    state.state.reset()
    storage.reset()
    yield
    state.state.reset()
    storage.reset()


# ── line protocol ──────────────────────────────────────────────────────────────────────────────

def test_line_protocol_reads_what_telegraf_writes():
    points, bad = lineproto.parse(
        'fb_if,device=sw\\ a,index=1,ifName=Gi1/0/1 '
        'ifOperStatus=1i,ifAlias="to \\"seat\\", A-1",up=true 1700000000000000000\n'
        "garbage\n"
        "# a comment\n"
        "cpu,cpu=cpu-total usage_idle=92.5\n")
    assert bad == 1 and len(points) == 2
    p = points[0]
    assert p.tags == {"device": "sw a", "index": "1", "ifName": "Gi1/0/1"}
    assert p.fields == {"ifOperStatus": 1, "ifAlias": 'to "seat", A-1', "up": True}
    assert p.time == 1700000000.0
    again, _ = lineproto.parse(lineproto.format_point(p))
    assert again[0] == p


# ── the picture of a switch from SNMP ──────────────────────────────────────────────────────────

def snmp_poll(at, in_octets, oper=1):
    return "\n".join([
        f"fb_system,{SW} sysName=\"sw-a-01.lan\",sysUpTime=123400i {int(at * 1e9)}",
        f"fb_if,{SW},index=10101,ifName=Gi1/0/1 ifOperStatus={oper}i,ifAdminStatus=1i,ifHighSpeed=1000i,"
        f"ifHCInOctets={in_octets}i,ifHCOutOctets={in_octets * 2}i,ifInErrors=0i,ifOutErrors=0i,"
        f"ifAlias=\"A-1\" {int(at * 1e9)}",
        f"fb_if,{SW},index=10148,ifName=Gi1/0/48 ifOperStatus=1i,ifAdminStatus=1i,ifHighSpeed=10000i,"
        f"ifHCInOctets=0i,ifHCOutOctets=0i {int(at * 1e9)}",
        f"fb_if,{SW},index=10101 dot3StatsDuplexStatus=3i {int(at * 1e9)}",
        f"fb_cpu,{SW},index=1 cpu=12i {int(at * 1e9)}",
    ])


def mac_tables(at):
    """Catalyst: one bridge per VLAN; MAC 02:00:00:00:00:07 on Gi1/0/1, many MACs on the uplink."""
    lines = [f"fb_bridge,{SW},vlan=10,index=1 ifIndex=10101i {int(at * 1e9)}",
             f"fb_bridge,{SW},vlan=10,index=48 ifIndex=10148i {int(at * 1e9)}",
             f"fb_fdb,{SW},vlan=10,index=2.0.0.0.0.7 dot1dTpFdbPort=1i,dot1dTpFdbStatus=3i {int(at * 1e9)}",
             f"fb_lldp,{SW},index=0.48.1 lldpRemSysName=\"core-01\",lldpRemPortId=\"Eth1/1\" {int(at * 1e9)}",
             f"fb_lldp_loc,{SW},index=48 lldpLocPortId=\"Gi1/0/48\" {int(at * 1e9)}"]
    # The core's MAC is learned on the uplink, and on the core the seat's MAC is on its downlink.
    lines.append(f"fb_fdb,{SW},vlan=10,index=2.0.0.0.0.1 dot1dTpFdbPort=48i {int(at * 1e9)}")
    lines.append(f"fb_qfdb,{CORE},index=10.2.0.0.0.0.7 dot1qTpFdbPort=1i {int(at * 1e9)}")
    lines.append(f"fb_bridge,{CORE},index=1 ifIndex=436207616i {int(at * 1e9)}")
    lines.append(f"fb_if,{CORE},index=436207616,ifName=Eth1/1 ifOperStatus=1i {int(at * 1e9)}")
    lines.append(f"fb_cdp,{CORE},index=436207616.1 "
                 f"cdpCacheDeviceId=\"sw-a-01\",cdpCacheDevicePort=\"Gi1/0/48\" {int(at * 1e9)}")
    lines.append(f"fb_arp,{CORE},index=436207616.192.0.2.40 mac=\"02:00:00:00:00:07\" {int(at * 1e9)}")
    return "\n".join(lines)


@pytest.fixture
def plugin(app_module, client):
    registry = app_module.app.extensions["floorbit_plugins"]
    assert client.put("/api/settings/plugins/telemetry", json={"enabled": True}).status_code == 200
    return registry.specs["telemetry"].plugin_class()(registry.context(registry.specs["telemetry"])) \
        if hasattr(registry, "context") else _plugin(registry)


def _plugin(registry):
    spec = registry.specs["telemetry"]

    class Call:
        def __getattr__(self, name):
            return lambda *a: registry.call(spec, name, *a)
    return Call()


def test_ports_rates_and_state_from_snmp(plugin):
    import time
    now = time.time()
    state.state.apply_text(snmp_poll(now - 30, 1000), now)
    state.state.apply_text(snmp_poll(now, 1000 + 30 * 125_000), now)   # 1 Mbit/s up, 2 down
    ports = {p["name"]: p for p in plugin.device_ports("sw-a-01")}
    assert list(ports) == ["Gi1/0/1", "Gi1/0/48"]                      # natural order
    seat = ports["Gi1/0/1"]
    assert seat["state"] == "up" and seat["speed_bps"] == 1e9 and seat["duplex"] == "full"
    assert seat["upload_bps"] == pytest.approx(1e6) and seat["download_bps"] == pytest.approx(2e6)
    assert seat["description"] == "A-1"
    details = plugin.device_details("SW-A-01.lan")        # by sysName too, any case
    assert details["status"] == "online" and details["cpu_load"] == 12 and details["up_ports"] == 2
    assert [d["hostname"] for d in plugin.devices()] == ["sw-a-01"]


def test_the_devices_widget_for_dashboards(plugin, client):
    import time
    assert client.get("/api/plugins/telemetry/widgets/devices").get_json()["sub"] == "No devices set up yet."
    now = time.time()
    state.state.apply_text(snmp_poll(now, 1000), now)
    w = client.get("/api/plugins/telemetry/widgets/devices").get_json()
    assert w["type"] == "status" and w["link"] == "/settings/telemetry"
    assert [(i["label"], i["state"]) for i in w["items"]] == [("sw-a-01", "up")] and w["sub"] == "1 of 1 up"


def test_a_counter_that_went_backwards_gives_no_rate(plugin):
    import time
    now = time.time()
    state.state.apply_text(snmp_poll(now - 30, 10_000_000), now)
    state.state.apply_text(snmp_poll(now, 5), now)          # cleared counters
    assert plugin.port_stats("sw-a-01", "gi1/0/1")["upload_bps"] == 0


def test_a_seat_ip_is_found_on_its_access_port_not_the_uplink(plugin):
    import time
    now = time.time()
    state.state.apply_text(snmp_poll(now, 1), now)
    state.state.apply_text(mac_tables(now), now)
    found = plugin.resolve_ip("192.0.2.40")
    assert found["mac"] == "02:00:00:00:00:07" and found["arp_source"] == "core-01"
    # The core learned it too, on its downlink to sw-a-01 (a CDP neighbour): that's not the seat.
    assert (found["hostname"], found["port"], found["vlan"]) == ("sw-a-01", "Gi1/0/1", "10")
    assert found["stats"]["state"] == "up"
    assert plugin.arp("02:00:00:00:00:07")[0]["ifName"] == "Eth1/1"
    assert {"port": "Gi1/0/1", "mac": "02:00:00:00:00:07", "vlan": "10"} in plugin.port_clients("sw-a-01")
    assert plugin.neighbours("sw-a-01") == [{"port": "Gi1/0/48", "remote": "core-01", "remote_port": "Eth1/1",
                                             "protocol": "lldp"}]
    assert plugin.neighbours("core-01")[0]["protocol"] == "cdp"


def test_old_table_rows_go(plugin):
    import time
    now = time.time()
    state.state.apply_text(mac_tables(now - state.TABLE_TTL - 5), now - state.TABLE_TTL - 5)
    state.state.apply([], now)
    assert plugin.arp("192.0.2.40") == []


def test_a_link_down_trap_changes_the_port_at_once(plugin):
    import time
    now = time.time()
    state.state.know([{"name": "sw-a-01", "address": "192.0.2.21", "drivers": ["snmp", "traps"]}])
    state.state.apply_text(snmp_poll(now, 1), now)
    state.state.apply_text('snmp_trap,source=192.0.2.21,oid=.1.3.6.1.6.3.1.1.5.3,driver=traps '
                           '.1.3.6.1.2.1.2.2.1.1.10101=10101i', now + 1)
    assert plugin.port_stats("sw-a-01", "Gi1/0/1")["state"] == "down"
    # Traps carry no token: one from an address nobody set up adds nothing.
    state.state.apply_text('snmp_trap,source=198.51.100.66,oid=.1.3.6.1.6.3.1.1.5.3,driver=traps '
                           '.1.3.6.1.2.1.2.2.1.1.1=1i', now + 2)
    state.state.apply_text('fb_mdt_if,mdt_source=rogue,name=Eth1/1 state/oper-status="UP"', now + 2)
    assert set(state.state.devices) == {"sw-a-01"}


def test_gnmi_and_mdt_interface_fields_by_meaning(plugin):
    import time
    now = time.time()
    state.state.know([{"name": "core-01", "address": "192.0.2.1", "mdt_node": "core-01", "drivers": ["gnmi", "mdt"]}])
    for at, octets in ((now - 10, 0), (now, 1_250_000)):
        state.state.apply_text(
            f'fb_gnmi_if,device=core-01,driver=gnmi,name=Ethernet1/1 oper_status="UP",admin_status="UP",'
            f'counters/in_octets={octets}i,counters/out_octets=0i,counters/in_errors=0i {int(at * 1e9)}', now)
    state.state.apply_text(
        'fb_mdt_if,mdt_source=core-01,name=Ethernet1/2 state/oper-status="DOWN" ' + str(int(now * 1e9)), now)
    ports = {p["name"]: p for p in plugin.device_ports("core-01")}
    assert ports["Ethernet1/1"]["upload_bps"] == pytest.approx(1e6) and ports["Ethernet1/1"]["state"] == "up"
    assert ports["Ethernet1/2"]["state"] == "down"


def test_a_firewalls_own_telegraf(plugin):
    import time
    now = time.time()
    state.state.apply_text("\n".join([
        "cpu,host=fw-01,cpu=cpu-total usage_idle=75",
        "mem,host=fw-01 used_percent=41.2",
        "pf,host=fw-01 entries=12345i,searches=1i",
        "net,host=fw-01,interface=igb0 bytes_recv=1i,bytes_sent=2i",
        'fb_gateway,device=fw-01,gateway=WAN_DHCP,driver=opnsense status="Online",delay_ms=4.1,loss_pct=0']), now)
    details = plugin.device_details("fw-01")
    assert details["cpu_load"] == 25 and details["mem_percent"] == 41 and details["states"] == 12345
    assert details["gateways"] == [{"name": "WAN_DHCP", "status": "Online", "delay_ms": 4.1, "loss_pct": 0.0}]
    assert plugin.devices()[0]["kind"] == "firewall"


# ── Telegraf's config ──────────────────────────────────────────────────────────────────────────

def test_telegraf_config_per_driver():
    catalyst = {"id": "a", "name": "sw-a-01", "address": "192.0.2.21", "drivers": ["snmp", "traps"],
                "platform": "ios", "snmp_version": "2c", "community": 'pub"lic', "fdb": "cisco_vlans",
                "vlans": [10, 20], "tables": True}
    nexus = {"id": "b", "name": "core-01", "address": "2001:db8::1", "drivers": ["snmp", "gnmi", "mdt"],
             "platform": "nxos", "snmp_version": "3", "sec_name": "fb", "auth_password": "a" * 12,
             "priv_password": "p" * 12, "fdb": "qbridge", "username": "telemetry", "password": "x"}
    conf = telegraf.render([catalyst, nexus], "http://agent:8186/write", "fbt_token")
    assert 'Authorization = "Token fbt_token"' in conf
    assert 'community = "pub\\"lic@10"' in conf and 'community = "pub\\"lic@20"' in conf
    assert conf.count('name = "fb_fdb"') == 2 and 'name = "fb_qfdb"' in conf
    assert 'agents = ["udp://[2001:db8::1]:161"]' in conf and 'sec_level = "authPriv"' in conf
    assert 'addresses = ["[2001:db8::1]:50051"]' in conf and 'origin = "openconfig"' in conf
    assert '[[inputs.snmp_trap]]' in conf and '[[inputs.cisco_telemetry_mdt]]' in conf
    assert 'conversion = "hwaddr"' in conf and 'name = "fb_cdp"' in conf
    import tomllib
    tomllib.loads(conf)                                  # Telegraf's config is TOML: it must parse
    paste = telegraf.device_config(nexus, "192.0.2.5")
    assert "ip address 192.0.2.5 port 57000" in paste and "feature grpc" in paste


# ── the API pollers ────────────────────────────────────────────────────────────────────────────

class FakeResp:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.ok = body, status, status < 400

    def json(self):
        return self.body


def test_nxapi_arp_and_interfaces(monkeypatch):
    answer = [
        {"id": 1, "result": {"body": {"TABLE_vrf": {"ROW_vrf": {"TABLE_adj": {"ROW_adj": [
            {"ip-addr-out": "192.0.2.40", "mac": "0200.0000.0007", "intf-out": "Vlan10"},
            {"ip-addr-out": "192.0.2.41", "mac": "INCOMPLETE", "intf-out": "Vlan10"}]}}}}}},
        {"id": 2, "result": {"body": {"TABLE_interface": {"ROW_interface": {
            "interface": "Ethernet1/1", "state": "up", "admin_state": "up", "eth_inbytes": "100",
            "eth_outbytes": "200", "eth_speed": "10 Gb/s", "desc": "to sw-a-01"}}}}}]
    seen = {}

    def post(self, url, json=None, headers=None, timeout=None):
        seen.update(url=url, cmds=[c["params"]["cmd"] for c in json], auth=self.auth)
        return FakeResp(answer)

    monkeypatch.setattr(pollers.requests.Session, "post", post)
    t = {"name": "core-01", "address": "192.0.2.1", "drivers": ["nxapi"], "username": "ro", "password": "pw"}
    points = pollers.nxapi(t, now=1000)
    assert seen == {"url": "https://192.0.2.1/ins", "cmds": ["show ip arp vrf all", "show interface"],
                    "auth": ("ro", "pw")}
    state.state.apply(points, 1000)
    dev = state.state.device("core-01")
    assert dev.arp == {"192.0.2.40": ["02:00:00:00:00:07", "Vlan10", 1000]}
    eth = dev.port(None, "Ethernet1/1")
    assert eth.oper == "up" and eth.speed == 10e9 and eth.alias == "to sw-a-01"


def test_opnsense_gateways(monkeypatch):
    bodies = {"/api/routes/gateway/status": {"items": [{"name": "WAN", "status_translated": "Online",
                                                         "delay": "3.2 ms", "loss": "0.0 %"}]},
              "/api/diagnostics/interface/getArp": [{"ip": "192.0.2.1", "mac": "02:00:00:00:00:01", "intf": "igb1"}],
              "/api/diagnostics/interface/getInterfaceStatistics": {"statistics": {}}}
    monkeypatch.setattr(pollers.requests.Session, "get",
                        lambda self, url, timeout=None, **kw: FakeResp(bodies[url.split("192.0.2.9")[1]]))
    t = {"name": "fw-01", "address": "192.0.2.9", "drivers": ["opnsense"], "username": "key", "api_secret": "s",
         "kind": "firewall"}
    state.state.apply(pollers.opnsense(t, now=5), 5)
    dev = state.state.device("fw-01")
    assert dev.gateways["WAN"]["delay_ms"] == 3.2 and dev.kind == "firewall" and "192.0.2.1" in dev.arp


def test_mdt_over_tls_when_a_certificate_is_set(monkeypatch):
    import tomllib
    t = {"name": "dist-02", "address": "192.0.2.22", "drivers": ["mdt"], "platform": "iosxe"}
    assert "tls_cert" not in telegraf.render([t], "http://x/write", "tok")
    monkeypatch.setenv("FLOORBIT_TELEGRAF_MDT_CERT", "/certs/mdt.pem")
    monkeypatch.setenv("FLOORBIT_TELEGRAF_MDT_KEY", "/certs/mdt.key")
    monkeypatch.setenv("FLOORBIT_TELEGRAF_MDT_CA", "/certs/ca.pem")
    mdt = tomllib.loads(telegraf.render([t], "http://x/write", "tok"))["inputs"]["cisco_telemetry_mdt"][0]
    assert mdt["tls_cert"] == "/certs/mdt.pem" and mdt["tls_allowed_cacerts"] == ["/certs/ca.pem"]
    assert "grpc-tls" in telegraf.device_config(t, "192.0.2.9")


def test_a_refused_login_is_named(monkeypatch):
    monkeypatch.setattr(pollers.requests.Session, "post", lambda *a, **k: FakeResp({}, 401))
    points, errors = pollers.poll_all([{"name": "core-01", "address": "192.0.2.1", "drivers": ["nxapi"]}],
                                      log=lambda *_: None)
    assert points == [] and "refused the login" in errors["core-01"]


def test_a_refused_login_is_not_tried_again_until_it_changes(monkeypatch):
    tries = []

    def refuse(*a, **k):
        tries.append(1)
        return FakeResp({}, 401)
    monkeypatch.setattr(pollers.requests.Session, "post", refuse)
    ctx = MemoryContext("telemetry")
    t = {"name": "core-01", "address": "192.0.2.1", "drivers": ["nxapi"], "username": "ro", "password": "old"}
    for _ in range(3):
        _, errors = pollers.poll_all([t], log=lambda *_: None, blocks=ctx)
    assert len(tries) == 1 and "not tried again" in errors["core-01"]
    assert ctx.auth.list()[0]["device"] == "core-01" and ctx.health_.report()["errors"]
    pollers.poll_all([{**t, "password": "new"}], log=lambda *_: None, blocks=ctx)    # edited: tried
    assert len(tries) == 2


# ── storage ────────────────────────────────────────────────────────────────────────────────────

def test_lite_rollups_in_sqlite_without_mac_tables(tmp_path):
    from floorbit import database
    db = database.Sql(f"sqlite:///{tmp_path / 'tele.db'}", str(tmp_path))
    store = storage.Storage(db)
    now = 1_800_000_000
    state.state.apply_text(snmp_poll(now - 30, 0), now)
    state.state.apply_text(snmp_poll(now, 30 * 125_000), now)
    state.state.apply_text(mac_tables(now), now)
    values = storage.snapshot(now=now)
    assert values["sw-a-01|Gi1/0/1|in_bps"] == pytest.approx(1e6) and values["sw-a-01||cpu"] == 12
    assert not any("02:00" in k or "192.0.2.40" in k for k in values)     # nobody's machine in a series
    store.sample(values, now)
    store.sample({"sw-a-01|Gi1/0/1|in_bps": 2e6}, now + 60)
    assert store.series("sw-a-01", "Gi1/0/1", "in_bps", hours=1, now=now + 60) == [[now, 1e6], [now + 60, 2e6]]
    store.prune(now + 7 * 3600)
    assert store.series("sw-a-01", "Gi1/0/1", "in_bps", hours=1, now=now + 7 * 3600) == []
    db.close()


def test_victoriametrics_gets_points_but_never_the_private_tables(monkeypatch):
    monkeypatch.setenv("FLOORBIT_VICTORIAMETRICS_URL", "http://vm.example:8428")
    sent = []

    def fake_post(url, data=None, timeout=None, **kw):
        sent.append((url, data.decode()))
        return FakeResp({}, 204)
    monkeypatch.setattr(storage.requests, "post", fake_post)
    points, _ = lineproto.parse(snmp_poll(1000, 1) + "\n" + mac_tables(1000))
    store = storage.Storage()
    store.forward_raw(points)
    url, body = sent[0]
    assert url == "http://vm.example:8428/write" and "fb_if" in body
    assert "fb_arp" not in body and "fb_fdb" not in body and "02:00" not in body
    store.sample({"sw-a-01|Gi1/0/1|in_bps": 5.0}, 1000)
    assert sent[1][1] == "fb_port_in_bps,device=sw-a-01,port=Gi1/0/1 value=5.0 1000000000000"


# ── the HTTP side ──────────────────────────────────────────────────────────────────────────────

def test_settings_intake_and_series(client, anon_client, tmp_path):
    made = client.post("/api/settings/telemetry/targets", json={
        "name": "sw-a-01", "address": "192.0.2.21", "drivers": ["snmp", "traps"], "platform": "ios",
        "community": "s3cret-community", "vlans": "10, 20"})
    assert made.status_code == 201, made.get_json()
    entry = made.get_json()
    assert entry["fdb"] == "cisco_vlans" and entry["vlans"] == [10, 20] and entry["secrets"] == ["community"]
    assert "s3cret" not in client.get("/api/settings/telemetry").get_data(as_text=True)
    bad = client.post("/api/settings/telemetry/targets", json={"name": "x y", "address": "1", "drivers": ["snmp"]})
    assert bad.status_code == 400
    token = client.get("/api/settings/telemetry/token").get_json()["token"]
    conf = client.get("/api/settings/telemetry/telegraf.conf").get_data(as_text=True)
    assert "s3cret-community@10" in conf and f"Token {token}" in conf
    # Telegraf, no account: the token or nothing.
    body = gzip.compress(snmp_poll(1000, 1).encode())
    assert anon_client.post("/api/telemetry/write", data=body, headers={"Content-Encoding": "gzip"}).status_code == 401
    ok = anon_client.post("/api/telemetry/write", data=body,
                          headers={"Content-Encoding": "gzip", "Authorization": f"Token {token}"})
    assert ok.status_code == 204
    # InfluxDB v1 senders (pfSense's Telegraf package): the token as the password.
    basic = base64.b64encode(f"floorbit:{token}".encode()).decode()
    assert anon_client.post("/api/telemetry/write", data=b"pf,host=fw-01 entries=1i",
                            headers={"Authorization": f"Basic {basic}"}).status_code == 204
    seen = client.get("/api/settings/telemetry").get_json()["seen"]
    assert seen["sw-a-01"]["ports"] == 2 and "fw-01" in seen
    config = client.get(f"/api/settings/telemetry/targets/{entry['id']}/device-config?collector=192.0.2.5")
    assert "snmp-server host 192.0.2.5" in config.get_json()["config"]
    assert client.get("/api/telemetry/series?device=sw-a-01&metric=nope").status_code == 400
    assert client.get("/api/telemetry/series?device=sw-a-01&port=Gi1/0/1&metric=in_bps").status_code == 200
    assert client.delete(f"/api/settings/telemetry/targets/{entry['id']}").status_code == 200
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert "Added telemetry from sw-a-01" in actions and "Looked at the telemetry token" in actions


def test_the_agent_gets_the_devices_and_sends_series(client, anon_client):
    from tests.test_agent import enrol
    key = enrol(client)["key"]
    head = {"Floorbit-Agent-Key": key}
    client.put("/api/settings/plugins/telemetry", json={"enabled": True})
    client.post("/api/settings/telemetry/targets", json={
        "name": "core-01", "address": "192.0.2.1", "drivers": ["nxapi"], "platform": "nxos",
        "username": "ro", "password": "nx-secret"})
    cfg = anon_client.get("/api/agent/v1/plugins", headers=head).get_json()["plugins"]["telemetry"]
    assert cfg["settings"]["targets"][0]["password"] == "nx-secret"     # opened for the agent only
    assert cfg["sends"] == {"series": {"privacy": "device"}, "endpoints": {"privacy": "device"}}
    import time
    sent = anon_client.post("/api/agent/v1/plugins/telemetry/series", headers=head, json={"payload": {
        "at": time.time(), "values": {"core-01|Eth1/1|in_bps": 1e6, "bad": 1}}})
    assert sent.status_code == 200 and sent.get_json() == {"taken": 1}
    # While an agent collects, Telegraf next to the hosted Floorbit is told to send there.
    token = client.get("/api/settings/telemetry/token").get_json()["token"]
    assert anon_client.post("/api/telemetry/write", data=b"pf,host=fw-01 entries=1i",
                            headers={"Authorization": f"Token {token}"}).status_code == 409


class AgentCtx(MemoryContext):
    tls = False

    def listen_http(self, port, handler, host="0.0.0.0", tls=False):
        self.handler = handler
        return port


def test_the_agent_part_collects_in_the_hall(tmp_path, monkeypatch):
    import gzip
    import importlib
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    monkeypatch.delenv("FLOORBIT_TELEGRAF_CONF", raising=False)
    target = {"id": "a1", "name": "sw-a-01", "address": "192.0.2.21", "kind": "switch", "platform": "ios",
              "drivers": ["snmp", "traps"], "snmp_version": "2c", "community": "example", "fdb": "cisco_vlans",
              "vlans": [10], "tables": True}
    ctx = AgentCtx("telemetry", {"targets": [target]}, {"sends": {"series": {"privacy": "device"}}},
                   state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        conf = (tmp_path / "telegraf.conf").read_text()
        token = (tmp_path / "ingest-token").read_text()
        assert token in conf and "udp://192.0.2.21:161" in conf and "http://agent:8186/write" in conf
        assert ctx.handler("POST", "/write", {"Authorization": "Token nope"}, b"x a=1")[0] == 401
        line = (b'fb_if,agent_host=192.0.2.21,ifIndex=1,ifName=Gi1/0/1 '
                b'ifHCInOctets=1000i,ifHCOutOctets=1000i,ifOperStatus=1i')
        status, _ = ctx.handler("POST", "/api/v2/write", {"Authorization": f"Token {token}",
                                                          "Content-Encoding": "gzip"}, gzip.compress(line))
        assert status == 204 and state.state.find("sw-a-01").interfaces
        plugin.send_series(time.time())
        kind, payload = ctx.sent[-1]
        assert kind == "series" and any(k.startswith("sw-a-01|Gi1/0/1|") for k in payload["values"])
        assert not any("fdb" in k or "arp" in k for k in payload["values"])
        plugin.report(time.time())
        report = ctx.health_.report()
        assert report["status"] == "ok" and report["metrics"]["points"] == 1
        # New devices from the hosted side: taken without a restart, Telegraf's config rewritten.
        assert plugin.configure({"targets": []}) is True
        assert "192.0.2.21" not in (tmp_path / "telegraf.conf").read_text()
    finally:
        ctx.stopping.set()


def test_plugins_can_add_measurements_and_drivers(monkeypatch):
    from floorbit.telemetry import targets
    monkeypatch.setattr(state, "_HANDLERS", dict(state._HANDLERS))
    monkeypatch.setattr(state, "PRIVATE", state.PRIVATE)
    monkeypatch.setattr(pollers, "POLLERS", dict(pollers.POLLERS))
    monkeypatch.setattr(targets, "DRIVERS", targets.DRIVERS)

    def ups(dev, point, at):
        dev.kind = "ups"
        dev.mem = point.fields.get("load")
        return True
    state.register("ups", ups)
    state.register("dhcp_lease", lambda dev, point, at: True, private=True)
    pollers.register("eaton", lambda t, now: [lineproto.Point("ups", {"device": t["name"]}, {"load": 40.0}, now)])
    assert "eaton" in targets.DRIVERS and "dhcp_lease" in state.PRIVATE
    points, errors = pollers.poll_all([{"name": "ups-1", "address": "192.0.2.50", "drivers": ["eaton"]}], now=1)
    state.state.apply(points, 1)
    assert errors == {} and state.state.device("ups-1").kind == "ups"


def test_a_standby_agent_listens_but_never_polls(tmp_path, monkeypatch):
    """Two agents sharing VIPs (VRRP): only the one with the first VIP polls and sends."""
    import importlib
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    monkeypatch.delenv("FLOORBIT_TELEGRAF_CONF", raising=False)
    target = {"id": "a1", "name": "sw-a-01", "address": "192.0.2.21", "kind": "switch", "platform": "ios",
              "drivers": ["snmp", "traps"], "snmp_version": "2c", "community": "example", "tables": True}
    ctx = AgentCtx("telemetry", {"targets": [target]}, {"sends": {"series": {"privacy": "device"}}},
                   state_dir=str(tmp_path), primary=False)
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        conf = (tmp_path / "telegraf.conf").read_text()
        assert "inputs.snmp]]" not in conf.replace("inputs.snmp_trap", "") and "inputs.snmp_trap" in conf
        assert state.state.collecting is False
        plugin.report(time.time())
        assert "standby" in ctx.health_.report()["message"]
        # The VIP moves here: polling goes into Telegraf's config at once.
        ctx.is_primary = True
        assert plugin.follow_role() is True and state.state.collecting is True
        assert "udp://192.0.2.21:161" in (tmp_path / "telegraf.conf").read_text()
        assert plugin.follow_role() is False
    finally:
        ctx.stopping.set()
        state.state.reset()


def test_telegraf_without_polling_or_listeners_still_starts():
    import tomllib
    conf = telegraf.render([{"name": "sw", "address": "192.0.2.1", "drivers": ["snmp"], "snmp_version": "2c",
                             "community": "example"}], "http://agent:8186/write", "t", poll=False)
    parsed = tomllib.loads(conf)
    assert list(parsed["inputs"]) == ["internal"] and parsed["inputs"]["internal"][0]["namedrop"] == ["*"]


def test_a_standby_picture_is_not_answered(plugin):
    now = time.time()
    state.state.apply_text(snmp_poll(now, 1000), now)
    assert plugin.devices()
    state.state.collecting = False
    try:
        assert plugin.devices() == [] and plugin.device_ports("sw-a-01") == [] and not plugin.device_details("sw-a-01")
    finally:
        state.state.collecting = True


def test_devices_from_the_inventory_are_collected_with_their_stored_logins(client, tmp_path, monkeypatch):
    """Inventory devices with the Telemetry feature on become targets: SNMP v3 for polling and
    traps, the API login for NX-API; a device set up on Settings > Telemetry by the same name wins."""
    from test_credentials import key_file
    from test_inventory_scope import add, put_cred, tag

    from floorbit import inventory_scope
    from floorbit.telemetry import targets
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "key"))
    inventory_scope._handed.clear()
    core = tag(client, name="core", features={"telemetry": True})
    nx = add(client, name="core-1", mgmt_ip="192.0.2.1", platform="NX-OS 10.3", tags=[core["id"]],
             properties={"telemetry_vlans": "10, 20"})
    add(client, name="sw-a-01", mgmt_ip="192.0.2.21", platform="IOS 15.2", tags=[core["id"]])
    add(client, name="sw-off", mgmt_ip="192.0.2.99")                        # feature off
    put_cred(client, owner_type="tag", owner_id=core["id"], kind="snmp_v3", username="mon",
             auth_protocol="SHA", priv_protocol="AES", secret="auth-pass-1", priv_secret="priv-pass-1")
    put_cred(client, owner_type="device", owner_id=nx["id"], kind="api", username="nxapi", secret="api-pass-1")
    found = {t["name"]: t for t in targets.from_inventory()}
    assert sorted(found) == ["core-1", "sw-a-01"]
    core1, sw = found["core-1"], found["sw-a-01"]
    assert core1["platform"] == "nxos" and core1["drivers"] == ["snmp", "traps", "nxapi"]
    assert core1["snmp_version"] == "3" and core1["sec_name"] == "mon" and core1["auth_password"] == "auth-pass-1"
    assert core1["username"] == "nxapi" and core1["password"] == "api-pass-1" and core1["vlans"] == [10, 20]
    assert core1["logins"]["api"]["device"] == nx["id"]
    assert sw["platform"] == "ios" and sw["fdb"] == "cisco_vlans" and sw["drivers"] == ["snmp", "traps"]
    conf = telegraf.render(targets.all_opened(), "http://agent:8186/write", "t")
    assert "udp://192.0.2.21:161" in conf and "auth-pass-1" in conf
    # The settings page lists them without secrets.
    listed = client.get("/api/settings/telemetry").get_json()["inventory"]
    assert {t["name"] for t in listed} == {"core-1", "sw-a-01"}
    assert "api-pass-1" not in json.dumps(listed) and "auth-pass-1" not in json.dumps(listed)
    # A device set up here by the same name wins.
    client.post("/api/settings/telemetry/targets", json={"name": "sw-a-01", "address": "192.0.2.22",
                                                         "drivers": ["snmp"], "community": "example"})
    assert [t["address"] for t in targets.all_opened() if t["name"] == "sw-a-01"] == ["192.0.2.22"]


def test_a_refused_inventory_login_blocks_the_stored_credential():
    target = {"name": "core-1", "address": "192.0.2.1", "drivers": ["nxapi"],
              "logins": {"api": {"device": "dev-1", "credential": "cred-1", "rev": "r1"}}}
    seen = []

    class Blocks:
        def may_login(self, device, credential, rev=None):
            seen.append(("may", device, credential, rev))
            return True

        def auth_failed(self, device, credential, rev=None, message=""):
            seen.append(("failed", device, credential, rev))

    def refuse(t, now):
        raise pollers.LoginRefused("core-1: NX-API refused the login (401)")
    old = pollers.POLLERS["nxapi"]
    pollers.POLLERS["nxapi"] = refuse
    try:
        pollers.poll_all([target], blocks=Blocks(), log=lambda *_: None)
    finally:
        pollers.POLLERS["nxapi"] = old
    assert seen == [("may", "dev-1", "cred-1", "r1"), ("failed", "dev-1", "cred-1", "r1")]
