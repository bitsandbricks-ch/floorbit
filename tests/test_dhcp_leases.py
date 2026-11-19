"""DHCP leases from the DHCP server's syslog as an IP to MAC source (issue #520)."""
import pytest

from floorbit import cache, dhcp_leases, sources, syslog
from floorbit.dhcp_leases import leases, parse

MAC = "02:00:00:00:00:1e"


@pytest.mark.parametrize("message, want", [
    ("DHCPACK on 192.0.2.40 to 02:00:00:00:00:1e (laptop) via eth1", ("grant", "192.0.2.40", MAC, None)),
    ("DHCPRELEASE of 192.0.2.40 from 02:00:00:00:00:1e (laptop) via eth1 (found)",
     ("release", "192.0.2.40", MAC, None)),
    ("DHCPACK(eth0) 192.0.2.40 02:00:00:00:00:1E laptop", ("grant", "192.0.2.40", MAC, None)),
    ("DHCPRELEASE(eth0) 192.0.2.40 02:00:00:00:00:1e", ("release", "192.0.2.40", MAC, None)),
    ("INFO  [kea-dhcp4.leases/812.140] DHCP4_LEASE_ALLOC [hwtype=1 02:00:00:00:00:1e], cid=[no info], "
     "tid=0x3d1d6b4e: lease 192.0.2.40 has been allocated for 3600 seconds", ("grant", "192.0.2.40", MAC, 3600)),
    ("DHCP4_RELEASE [hwtype=1 02:00:00:00:00:1e], cid=[no info], tid=0x1: address 192.0.2.40 was released properly.",
     ("release", "192.0.2.40", MAC, None)),
    ("dhcp1 assigned 192.0.2.40 to 02-00-00-00-00-1E", ("grant", "192.0.2.40", MAC, None)),
    ("dhcp1 deassigned 192.0.2.40 from 02:00:00:00:00:1e", ("release", "192.0.2.40", MAC, None)),
])
def test_the_lease_lines_of_common_dhcp_servers(message, want):
    assert parse(message) == want


@pytest.mark.parametrize("message", [
    "DHCPACK on 192.0.2.40",                                   # no MAC
    "DHCPACK to 192.0.2.40 (02:00:00:00:00:1e) via eth1",       # an INFORM answer: no lease
    "DHCPOFFER on 192.0.2.40 to 02:00:00:00:00:1e via eth1",     # offered, not taken
    "DHCPACK on 999.0.2.40 to 02:00:00:00:00:1e via eth1",
    "DHCPACK on 0.0.0.0 to 02:00:00:00:00:1e via eth1",
    "Interface Gi1/0/4, changed state to down",
])
def test_other_lines_are_no_lease(message):
    assert parse(message) is None


def test_a_lease_answers_ip_to_mac_until_released():
    leases.observe("DHCPACK on 192.0.2.40 to 02:00:00:00:00:1e via eth1", now=100)
    assert leases.mac_for_ip("192.0.2.40") == MAC and leases.ip_for_mac("02-00-00-00-00-1E") == "192.0.2.40"
    # The machine gets another address: the old one no longer points at it.
    leases.observe("DHCPACK on 192.0.2.41 to 02:00:00:00:00:1e via eth1")
    assert leases.mac_for_ip("192.0.2.40") is None and leases.ip_for_mac(MAC) == "192.0.2.41"
    # Another machine gets that address: the first machine keeps no stale claim to it.
    leases.observe("DHCPACK on 192.0.2.41 to 02:00:00:00:00:2a via eth1")
    assert leases.mac_for_ip("192.0.2.41") == "02:00:00:00:00:2a" and leases.ip_for_mac(MAC) is None
    # A release of an address someone else holds now changes nothing.
    leases.observe("DHCPRELEASE of 192.0.2.41 from 02:00:00:00:00:1e via eth1")
    assert leases.mac_for_ip("192.0.2.41") == "02:00:00:00:00:2a"
    leases.observe("DHCPRELEASE of 192.0.2.41 from 02:00:00:00:00:2a via eth1")
    assert leases.mac_for_ip("192.0.2.41") is None
    assert leases.status()["granted"] == 3 and leases.status()["released"] == 2


def test_a_lease_runs_out(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(dhcp_leases.time, "time", lambda: clock[0])
    leases.observe("DHCP4_LEASE_ALLOC [hwtype=1 02:00:00:00:00:1e], cid=[no info], tid=0x1: lease 192.0.2.40 "
                   "has been allocated for 600 seconds")
    clock[0] += 599
    assert leases.mac_for_ip("192.0.2.40") == MAC
    clock[0] += 2
    assert leases.mac_for_ip("192.0.2.40") is None


def test_leases_are_shared_through_valkey(app_module, monkeypatch):
    from conftest import FakeRedis
    fake = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", cache.Prefixed(fake, "default:"))
    leases.observe("DHCPACK(eth0) 192.0.2.40 02:00:00:00:00:1e laptop")
    assert fake.store["default:dhcp:ip:192.0.2.40"] == MAC
    assert "laptop" not in str(fake.store)                   # the host name isn't kept
    leases.reset()                                           # another pod: nothing in its memory
    assert leases.mac_for_ip("192.0.2.40") == MAC


def test_syslog_lines_feed_the_monitoring_lookups(app_module, tmp_path):
    receiver = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    receiver.receive(b"<30>dhcpd[812]: DHCPACK on 192.0.2.40 to 02:00:00:00:00:1e via eth1", "192.0.2.9",
                     check=False, device="dhcp-01")
    # A late line (kept by an agent while the uplink was down) could undo a newer lease: not taken.
    receiver.receive(b"<30>dhcpd[812]: DHCPACK on 192.0.2.50 to 02:00:00:00:00:1e via eth1", "192.0.2.9",
                     check=False, device="dhcp-01", late=True)
    assert receiver.status()["leases"]["granted"] == 1
    with app_module.app.app_context():
        monitor = sources.monitoring()
        assert monitor.mac_for_ip("192.0.2.40") == MAC and monitor.ip_for_mac(MAC) == "192.0.2.40"
        assert monitor.mac_for_ip("192.0.2.99") is None


def test_a_lease_wins_over_arp(app_module, monkeypatch):
    class Arp(sources.PluginMonitoring):
        def __init__(self):
            self.name, self.label = "fake", "Fake"

        def arp(self, query):
            return [{"ipv4_address": "192.0.2.40", "mac_address": "02:00:00:00:00:99"}]

    monitor = Arp()
    assert monitor.mac_for_ip("192.0.2.40") == "02:00:00:00:00:99"     # ARP alone
    leases.observe("DHCPACK on 192.0.2.40 to 02:00:00:00:00:1e via eth1")
    assert monitor.mac_for_ip("192.0.2.40") == MAC                      # the fresher lease
