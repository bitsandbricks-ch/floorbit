"""LibreNMS supplies discovery's facts (issue #966): VLANs, networks, optics and per-port mac, ips,
vlan and mode, against a fake LibreNMS (no network); and discovery takes them when the monitoring
rows carry none."""
import pytest
import requests
from conftest import FakeRedis

from floorbit import cache, sources
from floorbit.builtin_plugins.librenms import client
from floorbit.runtime import rt

DEVICES = [{"device_id": 2, "display": "sw-a-01", "hostname": "198.51.100.11", "sysName": "sw-a-01", "status": 1}]
PORTS = [
    {"port_id": 1, "ifIndex": 10101, "ifName": "Gi1/0/1", "ifOperStatus": "up", "ifSpeed": 1_000_000_000,
     "ifPhysAddress": "0200000a0001", "ifVlan": "10", "ifTrunk": None},
    {"port_id": 49, "ifIndex": 10149, "ifName": "Te1/1/1", "ifOperStatus": "up", "ifSpeed": 10_000_000_000,
     "ifPhysAddress": "02:00:00:0a:00:31", "ifVlan": "1", "ifTrunk": "dot1Q"},
    {"port_id": 90, "ifIndex": 90, "ifName": "Vlan10", "ifOperStatus": "up", "ifSpeed": 1_000_000_000,
     "ifPhysAddress": "000000000000", "ifVlan": "", "ifTrunk": ""},
]
ADDRESSES = [
    {"ipv4_address": "192.0.2.1", "ipv4_prefixlen": 24, "port_id": 90},
    {"ipv4_address": "198.51.100.11", "ipv4_prefixlen": 32, "port_id": 90},      # a /32: no network
    {"ipv6_address": "2001:0db8:0000:0000:0000:0000:0000:0001", "ipv6_prefixlen": 64, "port_id": 90},
]
VLANS = [{"vlan_vlan": 1, "vlan_name": "default"}, {"vlan_vlan": 10, "vlan_name": " seats "},
         {"vlan_vlan": 1002, "vlan_name": "fddi-default"}, {"vlan_vlan": "x", "vlan_name": "junk"}]
TRANSCEIVERS = [{"port_id": 49, "model": "SFP-10G-SR", "serial": "AVX0001", "vendor": "CISCO", "type": "SFP+"},
                {"port_id": 1, "model": "no serial", "serial": ""}]
ENTITY = [{"entPhysicalClass": "module", "entPhysicalModelName": "GLC-SX-MMD", "entPhysicalSerialNum": "FNS0001",
           "entPhysicalDescr": "1000BaseSX SFP", "entPhysicalName": "GigabitEthernet1/1/1", "ifIndex": 10149},
          {"entPhysicalClass": "chassis", "entPhysicalModelName": "WS-C2960X", "entPhysicalSerialNum": "FOC1"}]


class Answer:
    def __init__(self, body, status=200):
        self.status_code, self.ok, self._body = status, status < 400, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code}")


class FakeLibreNMS:
    def __init__(self):
        self.asked = []
        self.old = False          # a LibreNMS without /transceivers and the newer port columns

    def __call__(self, url, headers=None, params=None, **kwargs):
        assert headers["X-Auth-Token"] == "token-example"
        path = url.removeprefix("https://librenms.example.com/api/v0/")
        self.asked.append(path)
        parts = path.split("/")
        if path == "devices":
            q = (params or {}).get("query", "")
            return Answer({"devices": [dict(d) for d in DEVICES if q in d["display"]]})
        if parts[0] == "devices" and parts[1] != "2":
            return Answer({"status": "error"}, 404)
        if parts[2:] == ["ports"]:
            columns = (params or {}).get("columns", "").split(",")
            if self.old and "ifTrunk" in columns:
                return Answer({"status": "error"}, 500)
            return Answer({"ports": [{k: v for k, v in p.items() if k in columns} for p in PORTS]})
        if parts[2:] == ["ip"]:
            return Answer({"addresses": ADDRESSES})
        if parts[2:] == ["vlans"]:
            return Answer({"vlans": VLANS})
        if parts[2:] == ["transceivers"]:
            return Answer({}, 404) if self.old else Answer({"transceivers": TRANSCEIVERS})
        if parts[0] == "inventory" and parts[2:] == ["all"]:
            return Answer({"inventory": ENTITY})
        return Answer({}, 404)


@pytest.fixture
def librenms(monkeypatch):
    fake = FakeLibreNMS()
    monkeypatch.setattr(client.requests, "get", fake)
    monkeypatch.setattr(rt, "librenms_url", "https://librenms.example.com")
    monkeypatch.setattr(rt, "librenms_token", "token-example")
    monkeypatch.setattr(cache, "redis_client", FakeRedis())
    client.reset_caches()
    yield fake
    client.reset_caches()


def test_librenms_says_what_a_switch_is_in_telemetrys_shape(librenms):
    facts = client.device_facts("sw-a-01")
    assert facts == {
        "vlans": {"1": "default", "10": "seats", "1002": "fddi-default"},
        "networks": ["192.0.2.0/24"],
        "transceivers": [{"port": "Te1/1/1", "model": "SFP-10G-SR", "descr": "CISCO SFP+", "serial": "AVX0001"}],
    }
    assert client.device_facts("not-in-librenms") == {}


def test_an_older_librenms_gives_its_optics_from_the_entity_inventory(librenms):
    librenms.old = True
    facts = client.device_facts("sw-a-01")
    assert facts["transceivers"] == [{"port": "Te1/1/1", "model": "GLC-SX-MMD", "descr": "1000BaseSX SFP",
                                      "serial": "FNS0001"}]
    assert facts["vlans"]["10"] == "seats"


def test_ports_carry_mac_ips_vlan_and_mode(librenms):
    ports = {p["name"]: p for p in client.fetch_device_ports("sw-a-01")}
    gi = ports["Gi1/0/1"]
    assert (gi["mac"], gi["vlan"], gi["mode"]) == ("02:00:00:0a:00:01", 10, "access")
    te = ports["Te1/1/1"]
    assert (te["mode"], te["vlan"]) == ("trunk", 1)
    svi = ports["Vlan10"]
    assert svi["ips"] == ["192.0.2.1/24", "198.51.100.11/32"]
    assert "mac" not in svi and "mode" not in svi
    assert gi["state"] == "up" and gi["speed_bps"] == 1e9
    # The addresses are kept a few minutes: the needs-attention watch reads ports often.
    librenms.asked.clear()
    client.fetch_device_ports("sw-a-01")
    assert not any(a.endswith("/ip") for a in librenms.asked)


def test_an_older_librenms_still_lists_its_ports(librenms):
    librenms.old = True
    ports = {p["name"]: p for p in client.fetch_device_ports("sw-a-01")}
    assert ports["Gi1/0/1"]["state"] == "up" and "mode" not in ports["Gi1/0/1"]
    assert ports["Vlan10"]["ips"] == ["192.0.2.1/24", "198.51.100.11/32"]


# ── discovery with LibreNMS alone ───────────────────────────────────────────────────────────────

class LibreNMSOnly(sources.NoMonitoring):
    """LibreNMS's rows: no ``facts``, only its own keys; facts come from device_facts()."""
    name = 'librenms'

    def __init__(self, facts):
        self.facts, self.asked = facts, []

    def enabled(self):
        return True

    def devices(self):
        return [{'hostname': 'sw-a-01', 'hardware': 'WS-C2960X-48FPD-L', 'os': 'ios', 'status': 1},
                {'hostname': 'fw-01', 'status': 1, 'facts': {'routes': [
                    {'network': '0.0.0.0/0', 'next_hop': '192.0.2.254', 'interface': 'wan', 'proto': 'static'}],
                    'networks': ['192.0.2.0/24']}}]

    def device_facts(self, hostname):
        self.asked.append(hostname)
        return self.facts.get(hostname, {})


def test_discovery_fills_vlans_networks_and_optics_from_librenms_alone(client):
    for body in ({'name': 'sw-a-01', 'role': 'switch'}, {'name': 'fw-01', 'role': 'firewall'}):
        assert client.post('/api/inventory', json=body).status_code == 201
    source = LibreNMSOnly({
        'sw-a-01': {'vlans': {'10': 'seats'}, 'networks': ['192.0.2.0/24'],
                    'transceivers': [{'port': 'Te1/1/1', 'model': 'SFP-10G-SR', 'descr': '', 'serial': 'AVX0001'}]},
        # The row's own facts win; what they don't say is filled in.
        'fw-01': {'networks': ['198.51.100.0/24'], 'vlans': {'30': 'crew'}},
    })
    before = sources.use(source)
    try:
        r = client.post('/api/inventory/sync')
        assert r.status_code == 200, r.data
        devices = {d['name']: d for d in client.get('/api/inventory').get_json()['devices']}
        sw = client.get(f"/api/inventory/{devices['sw-a-01']['id']}").get_json()
        fw = client.get(f"/api/inventory/{devices['fw-01']['id']}").get_json()
    finally:
        sources.use(before)
    assert sorted(source.asked) == ['fw-01', 'sw-a-01']
    assert sw['model'] == 'WS-C2960X-48FPD-L' and sw['platform'] == 'Cisco IOS'   # identity as before
    assert sw['discovered']['vlans'] == [{'id': 10, 'name': 'seats'}]
    assert sw['discovered']['networks'] == ['192.0.2.0/24']
    assert sw['discovered']['transceivers'][0]['serial'] == 'AVX0001'
    assert fw['discovered']['networks'] == ['192.0.2.0/24']
    assert fw['discovered']['vlans'] == [{'id': 30, 'name': 'crew'}]
    assert fw['discovered']['routes'][0]['next_hop'] == '192.0.2.254'


def test_a_source_that_fails_its_facts_does_not_stop_discovery(client):
    assert client.post('/api/inventory', json={'name': 'sw-a-01', 'role': 'switch'}).status_code == 201

    class Broken(LibreNMSOnly):
        def device_facts(self, hostname):
            raise RuntimeError('LibreNMS went away')

    before = sources.use(Broken({}))
    try:
        r = client.post('/api/inventory/sync')
        report = next(x for x in r.get_json()['reports'] if x['plugin'] == 'discovery')
    finally:
        sources.use(before)
    assert report['received'] == 1 and not report.get('error')


# ── which plugin answers ────────────────────────────────────────────────────────────────────────

class Spec:
    def __init__(self, id_, facts, set_up=True):
        self.id, self.name = id_, id_
        self.facts, self.set_up = facts, set_up

    def plugin_class(self):
        facts, set_up = self.facts, self.set_up

        class P:
            def configured(self):
                return set_up

            def device_facts(self, hostname):
                return facts
        return P


class Registry:
    def __init__(self, specs):
        self.specs = specs

    def monitoring_sources(self):
        return self.specs

    def monitoring_source(self):
        return self.specs[0]

    def call(self, spec, method, *args):
        return getattr(spec.plugin_class()(), method)(*args)


def test_telemetry_facts_come_first_and_librenms_fills_the_gaps():
    librenms = Spec('librenms', {'vlans': {'10': 'from librenms'}, 'transceivers': [{'serial': 'X'}]})
    telemetry = Spec('telemetry', {'vlans': {'10': 'seats'}, 'routes': []})
    off = Spec('prometheus', {'networks': ['203.0.113.0/24']}, set_up=False)
    registry = Registry([librenms, telemetry, off])
    got = sources.PluginMonitoring(registry, librenms).device_facts('sw-a-01')
    assert got == {'vlans': {'10': 'seats'}, 'transceivers': [{'serial': 'X'}]}
    # The agent's executor answers the same way.
    assert sources.call_monitoring(registry, 'device_facts', 'sw-a-01') == got


def test_demo_data_answers_alone():
    demo = Spec('demo', {'vlans': {'1': 'demo'}})
    registry = Registry([demo, Spec('telemetry', {'networks': ['192.0.2.0/24']})])
    assert sources.PluginMonitoring(registry, demo).device_facts('sw') == {'vlans': {'1': 'demo'}}
