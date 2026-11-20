"""The seat port config check from the config backups (issue #1059)."""
import pytest

from floorbit import config_backup, port_config
from floorbit.store import load_data
from integrations import seat_sources

CONFIG = """Building configuration...
!
hostname sw-a-01
spanning-tree mode rapid-pvst
!
interface GigabitEthernet1/0/1
 description Seat A-1
 switchport access vlan 100
 switchport mode access
 spanning-tree portfast
 spanning-tree bpduguard enable
 storm-control broadcast level 1.00
!
interface GigabitEthernet1/0/2
 switchport access vlan 100
 switchport mode access
 spanning-tree portfast
 storm-control broadcast level 1.00
!
interface GigabitEthernet1/0/3
 switchport access vlan 100
 switchport mode access
 spanning-tree portfast
 storm-control broadcast level 1.00
!
interface GigabitEthernet1/0/4
 switchport mode access
 spanning-tree portfast
 spanning-tree bpduguard enable
 storm-control broadcast level 1.00
!
interface GigabitEthernet1/0/5
 switchport access vlan 100
 switchport mode access
 spanning-tree portfast
 spanning-tree bpduguard enable
 storm-control broadcast level 1.00
!
interface TenGigabitEthernet1/1/1
 switchport mode trunk
!
end
"""
MAPPING = {f"A-{n}": {"switch": "sw-a-01", "port": f"Gi1/0/{n}"} for n in range(1, 6)}
MAPPING["B-1"] = {"switch": "sw-b-01", "port": "Gi1/0/1"}   # no copy yet


@pytest.fixture
def copies(tmp_path, monkeypatch):
    monkeypatch.setattr(config_backup, "folder", lambda: str(tmp_path / "configs"))
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: MAPPING)
    port_config._parsed.clear()
    config_backup.save("sw-a-01", CONFIG, "test", now=1000)


def _findings(result, switch="sw-a-01"):
    return {f["rule"]: f for s in result["switches"] if s["switch"] == switch for f in s["findings"]}


def test_ports_are_the_same_however_they_are_written():
    assert port_config.port_key("GigabitEthernet1/0/3") == port_config.port_key("gi1/0/3") == "gi1/0/3"
    assert port_config.port_key("TwentyFiveGigE1/0/1") != port_config.port_key("TwoGigabitEthernet1/0/1")
    assert port_config.port_key("Ethernet1/12") == port_config.port_key("Eth1/12")


def test_the_check_finds_the_ports_that_break_a_rule_with_the_fix(copies):
    result = port_config.check({}, MAPPING)
    [sw] = [s for s in result["switches"] if s["switch"] == "sw-a-01"]
    assert (sw["seat_ports"], sw["checked"]) == (5, 5)
    found = _findings(result)
    assert set(found) == {"bpduguard", "vlan"}       # the uplink is no seat port, so it isn't checked
    assert found["bpduguard"]["ports"] == ["GigabitEthernet1/0/2 - 3"]
    assert found["bpduguard"]["fix"] == ["interface range GigabitEthernet1/0/2 - 3", " spanning-tree bpduguard enable"]
    assert found["vlan"]["ports"] == ["GigabitEthernet1/0/4"] and found["vlan"]["vlan"] == 100
    assert found["vlan"]["fix"][1] == " switchport access vlan 100"
    assert result["no_copy"] == ["sw-b-01"]


def test_a_global_default_counts_for_every_port(copies):
    default = "spanning-tree mode rapid-pvst\nspanning-tree portfast bpduguard default"
    config_backup.save("sw-a-01", CONFIG.replace("spanning-tree mode rapid-pvst", default), "test", now=2000)
    assert "bpduguard" not in _findings(port_config.check({}, MAPPING))


def test_rules_can_be_turned_off_for_the_event(copies):
    data = {}
    assert port_config.set_off(data, ["vlan", "vlan"]) == ["vlan"]
    assert set(_findings(port_config.check(data, MAPPING))) == {"bpduguard"}
    with pytest.raises(port_config.PortCheckError):
        port_config.set_off(data, ["nope"])


def test_a_rule_no_switch_follows_is_said_once():
    result = {"switches": [
        {"switch": s, "checked": 4,
         "findings": [{"rule": "storm", "label": "storm control", "count": 4, "ports": ["x"]}]}
        for s in ("sw-1", "sw-2")]}
    assert [p["title"] for p in port_config.problems(result)] == ["No switch has storm control on its seat ports"]
    result["switches"][0]["findings"][0]["count"] = 2
    assert [p["title"] for p in port_config.problems(result)] == [
        "sw-1: 2 seat ports without storm control", "sw-2: 4 seat ports without storm control"]


def test_the_api_and_problems(client, copies):
    body = client.get("/api/configs/port-check").get_json()
    assert set(_findings(body)) == {"bpduguard", "vlan"}
    attention = client.get("/api/problems").get_json()["attention"]
    titles = {p["title"] for p in attention if p["kind"] == "portconfig"}
    assert titles == {"sw-a-01: 2 seat ports without BPDU guard", "sw-a-01: 1 seat port not in VLAN 100"}
    de = client.get("/api/problems", headers={"Accept-Language": "de-CH"}).get_json()["attention"]
    assert "sw-a-01: 2 Platz-Ports ohne BPDU guard" in {p["title"] for p in de}
    assert client.put("/api/configs/port-check", json={"off": ["bad"]}).status_code == 400
    assert client.put("/api/configs/port-check", json={"off": ["vlan"]}).get_json()["off"] == ["vlan"]
    assert load_data()["port_check"]["off"] == ["vlan"]


def test_a_viewer_cannot_read_the_check(kiosk_client, copies):
    assert kiosk_client.get("/api/configs/port-check").status_code == 403
