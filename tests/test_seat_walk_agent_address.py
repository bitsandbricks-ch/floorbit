"""The seat walk works out where laptops reach an agent from what connected agents report, with
nothing typed in (issue #1424): a VIP the pair holds, else an address on an agent's certificate."""
import pytest

from floorbit import agent_link, seat_walk


@pytest.fixture(autouse=True)
def no_checkin_name(monkeypatch):
    monkeypatch.delenv("CHECKIN_ADDRESS", raising=False)


def _agents(monkeypatch, *reports):
    monkeypatch.setattr(agent_link, "all_agents", lambda: [{"connected": True, "report": r} for r in reports])


def test_the_vip_the_pair_holds(client, monkeypatch):
    cert = {"settings": {"cert": {"names": ["agent-b.example.com", "192.0.2.22"]}}}
    _agents(monkeypatch, {**cert, "vrrp": {"primary": False, "holds": []}},
            {"vrrp": {"primary": True, "holds": ["192.0.2.20"]}, "front_door_ports": {"https": 8443}})
    with client.application.app_context():
        assert seat_walk.agent_url() == "https://192.0.2.20:8443"
        assert seat_walk.agents_connected() == 2


def test_an_address_on_the_agents_certificate(client, monkeypatch):
    # Names and public addresses are left out: a laptop in the hall only reaches the agent's own.
    _agents(monkeypatch, {"settings": {"cert": {"names": ["agent.example.com", "8.8.8.8", "127.0.0.1", "10.20.0.7"]}}})
    with client.application.app_context():
        assert seat_walk.agent_url() == "https://10.20.0.7"


def test_nothing_reported_and_no_agent(client, monkeypatch):
    _agents(monkeypatch, {"vrrp": {"holds": ["203.0.113.300"]}})
    with client.application.app_context():
        assert seat_walk.agent_url() == ""
    _agents(monkeypatch)
    with client.application.app_context():
        assert seat_walk.agents_connected() == 0
        assert client.get("/api/seat-walk").get_json()["agents_connected"] == 0
