"""The LibreNMS client against a fake LibreNMS (no network): which device a switch name means, and
IP to switch port (core ARP, then the access switch's MAC table, uplinks left out)."""
import json

import pytest
import requests
from conftest import FakeRedis

from floorbit import cache
from floorbit.builtin_plugins.librenms import client
from floorbit.runtime import rt

IP, MAC = "192.0.2.10", "aa:bb:cc:00:00:01"
DEVICES = [
    {"device_id": 1, "display": "core", "hostname": "core.example.com", "sysName": "core", "status": 1},
    {"device_id": 2, "display": "sw-a1", "hostname": "198.51.100.11", "sysName": "sw-a1", "status": 1},
    {"device_id": 3, "display": "sw-a10", "hostname": "198.51.100.20", "sysName": "sw-a10", "status": 0},
]
# Every switch between the core and the seat learns the MAC: the core on its trunk, sw-a1 on its
# uplink and on the seat's port.
FDB = [
    {"hostname": "core.example.com", "sysName": "core", "port_id": 10, "ifName": "Te1/1/1",
     "ifAlias": "to sw-a1", "ifIndex": 101, "vlan": 20},
    {"hostname": "198.51.100.11", "sysName": "sw-a1", "port_id": 48, "ifName": "Te1/0/48",
     "ifAlias": "Uplink core", "ifIndex": 148, "vlan": 20},
    {"hostname": "198.51.100.11", "sysName": "sw-a1", "port_id": 7, "ifName": "Gi1/0/7",
     "ifAlias": "", "ifIndex": 107, "vlan": 20},
]
MAC_TABLES = {   # by device: the core's trunk carries the whole hall
    "1": [{"port_id": 10, "mac_address": f"aa:bb:cc:00:01:{i:02x}"} for i in range(40)],
    "2": [{"port_id": 48, "mac_address": f"aa:bb:cc:00:02:{i:02x}"} for i in range(30)]
         + [{"port_id": 7, "mac_address": MAC}],
}
PORTS = {"2": [{"ifName": "Gi1/0/7", "ifOperStatus": "up", "ifSpeed": 1_000_000_000,
                "ifInOctets_rate": 1000, "ifOutOctets_rate": 4000}]}


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
        self.down = False

    def __call__(self, url, headers=None, params=None, **kwargs):
        assert headers["X-Auth-Token"] == "token-example"
        path = url.removeprefix("https://librenms.example.com/api/v0/")
        self.asked.append(path)
        if self.down:
            raise requests.ConnectionError("refused")
        parts = path.split("/")
        if path == "devices":
            q = (params or {}).get("query", "")
            return Answer({"devices": [d for d in DEVICES if q in d["display"] or q in d["hostname"]]})
        if parts[:3] == ["resources", "ip", "arp"]:
            rows = [{"ipv4_address": IP, "mac_address": MAC, "hostname": "core.example.com"}]
            return Answer({"arp": [r for r in rows if parts[3] in (r["ipv4_address"], r["mac_address"])]})
        if parts[:2] == ["resources", "fdb"]:
            return Answer({"ports_fdb": FDB if parts[2] == MAC else []})
        if parts[0] == "devices" and parts[2:] == ["fdb"]:
            return Answer({"ports_fdb": MAC_TABLES.get(parts[1], [])})
        if parts[0] == "devices" and parts[2:] == ["ports"]:
            return Answer({"ports": PORTS.get(parts[1], [])})
        return Answer({}, 404)


@pytest.fixture
def librenms(monkeypatch):
    fake = FakeLibreNMS()
    monkeypatch.setattr(client.requests, "get", fake)
    monkeypatch.setattr(rt, "librenms_url", "https://librenms.example.com")
    monkeypatch.setattr(rt, "librenms_token", "token-example")
    monkeypatch.setattr(rt, "librenms_fdb_exclude", [])
    monkeypatch.setattr(cache, "redis_client", FakeRedis())
    return fake


def test_a_switch_name_means_that_switch_not_one_that_starts_like_it():
    assert client.best_device(DEVICES[::-1], "sw-a1")["device_id"] == 2      # whatever the order
    assert client.best_device(DEVICES, "SW-A1.example.com")["device_id"] == 2   # short name
    assert client.best_device(DEVICES, "core.example.com")["device_id"] == 1    # hostname
    assert client.best_device(DEVICES, "a10")["device_id"] == 3                 # the only one with it
    assert client.best_device(DEVICES, "sw-a") is None                         # two: don't guess
    assert client.best_device(DEVICES, "") is None


def test_an_ip_resolves_to_the_access_port_not_an_uplink(librenms):
    got = client.resolve_ip_to_switch_port(IP)
    assert (got["mac"], got["device_name"], got["hostname"], got["port"], got["vlan"]) == \
        (MAC, "sw-a1", "198.51.100.11", "Gi1/0/7", 20)
    assert got["macs_on_port"] == 1 and got["arp_source"] == "core.example.com"
    assert got["stats"]["speed_bps"] == 1_000_000_000

    librenms.asked.clear()
    again = client.resolve_ip_to_switch_port(IP)       # where it sits comes from the cache
    assert again["port"] == "Gi1/0/7"
    assert not any(a.startswith("resources/") for a in librenms.asked)
    assert any(a.endswith("/ports") for a in librenms.asked)   # its numbers stay live


def test_an_ip_nobody_has_seen_is_none(librenms):
    assert client.resolve_ip_to_switch_port("192.0.2.99") is None


def test_librenms_away_is_none_not_an_error(librenms):
    librenms.down = True
    assert client.resolve_ip_to_switch_port(IP) is None
    assert client.fetch_librenms_details("sw-a1") == {"status": "unknown", "hostname": "sw-a1"}
    assert client.fetch_librenms_mac_table("sw-a1") == []


def test_a_broken_redis_does_not_stop_the_lookup(librenms, monkeypatch):
    import redis

    class Broken(FakeRedis):
        def get(self, key):
            raise redis.ConnectionError("gone")

    monkeypatch.setattr(cache, "redis_client", Broken())
    assert client.resolve_ip_to_switch_port(IP)["port"] == "Gi1/0/7"


def test_a_garbled_cache_entry_is_looked_up_again(librenms):
    cache.redis_client.set(f"resolve:{IP}", "{not json")
    assert client.resolve_ip_to_switch_port(IP)["port"] == "Gi1/0/7"
    assert json.loads(cache.redis_client.get(f"resolve:{IP}"))["port"] == "Gi1/0/7"


def test_names_from_elsewhere_stay_one_path_segment(librenms):
    assert client.arp_entries("../devices") == []
    assert "resources/ip/arp/..%2Fdevices" in librenms.asked


def test_switch_details_from_the_device_and_its_ports(librenms):
    got = client.fetch_librenms_details("sw-a1")
    assert got["status"] == "online" and got["up_ports"] == 1 and got["total_ports"] == 1
    assert got["total_traffic_bps"] == 40_000
    assert client.fetch_librenms_details("sw-a10")["status"] == "offline"
    assert client.fetch_librenms_details("sw-b1") == {"status": "unknown", "hostname": "sw-b1"}
