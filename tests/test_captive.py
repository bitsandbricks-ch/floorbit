"""What the agent's Captive Portal API is told (issue #473, floorbit/captive.py)."""
from floorbit import port_clients
from integrations import checkin
from tests.test_agent import clean_tunnel, enrol  # noqa: F401  # the fixture resets the tunnel


def test_the_agent_learns_which_ips_are_done(client, app_module, monkeypatch, tmp_path):
    monkeypatch.setenv("CHECKIN_FILE", str(tmp_path / "checkins.json"))
    monkeypatch.setenv("CHECKIN_VALIDATE_SEATS", "false")
    monkeypatch.setenv("PUBLIC_URL", "https://floor.example.com/")
    key = enrol(client)["key"]
    agent = app_module.app.test_client()
    h = {"Floorbit-Agent-Key": key}
    assert agent.get("/api/agent/v1/captive").status_code == 401
    monkeypatch.setenv("CHECKIN_ENABLED", "false")
    off = agent.get("/api/agent/v1/captive", headers=h)
    assert off.status_code == 409 and "Check-in" in off.get_json()["error"]

    monkeypatch.setenv("CHECKIN_ENABLED", "true")
    off = agent.get("/api/agent/v1/captive", headers=h)      # off by default, even with check-in on
    assert off.status_code == 409 and "captive portal" in off.get_json()["error"]
    monkeypatch.setenv("CAPTIVE_ENABLED", "true")
    checkin.check_in("A-1", "player1", "192.0.2.10", lambda: {}, mac="02:00:00:00:00:01")
    finder = app_module.app.extensions["floorbit_port_clients"]
    asked = []
    monkeypatch.setattr(finder, "request", lambda: asked.append(1))
    # The last MAC table read: A-1's port now has another machine (a new MAC, a new lease),
    # and B-2's port has one, but B-2 never checked in.
    monkeypatch.setattr(finder, "seat_ips", {"192.0.2.11": "A-1", "192.0.2.20": "B-2"})
    body = agent.get("/api/agent/v1/captive", headers=h).get_json()
    assert body == {"done": ["192.0.2.10", "192.0.2.11"], "portal_url": "https://floor.example.com/checkin"}
    assert asked == [1]


class Monitor:
    def enabled(self):
        return True

    def port_clients(self, switch):
        return [{"port": "Gi1/0/1", "mac": "02:00:00:00:00:01"}, {"port": "Gi1/0/9", "mac": "02:00:00:00:00:09"}]

    def arp(self, net):
        return [{"mac_address": "02:00:00:00:00:01", "ipv4_address": "192.0.2.10"},
                {"mac_address": "02:00:00:00:00:09", "ipv4_address": "192.0.2.90"}]


def test_a_mac_table_read_keeps_the_ips_on_seat_ports(monkeypatch):
    from floorbit import sources
    from integrations import seat_sources
    data = {"cables": [{"switch": "sw-a-01", "port": "Gi1/0/1", "seat": "a-1", "label": "C-0001"}]}
    seats = {"A-1": {"ip_address": "192.0.2.10"}}
    found = port_clients.find(Monitor(), data, seats)
    assert found["seat_ips"] == {"192.0.2.10": "A-1"}        # the unplanned port's IP is no seat's
    monkeypatch.setattr(sources, "monitoring", Monitor)
    monkeypatch.setattr(port_clients, "load_data", lambda: data)
    monkeypatch.setattr(seat_sources, "load", lambda: seats)
    finder = port_clients.Finder()
    finder.run(now=1)
    assert finder.seat_ips == {"192.0.2.10": "A-1"} and "seat_ips" not in finder.state()
    finder.reset()
    assert finder.seat_ips == {}
