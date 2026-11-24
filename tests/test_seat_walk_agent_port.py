"""Where the seat walk sends laptops when the agent's front door isn't on 443/80 (issue #1361):
compose passes the published ports in and the agent reports them; "Reached in the hall at" on the
agent's page names it outright."""
import pytest

from floorbit import agent_link, seat_walk
from tests.test_agent import enrol


@pytest.fixture(autouse=True)
def clean_tunnel():
    agent_link.tunnel.reset()
    agent_link._forget_cache()
    yield
    agent_link.tunnel.reset()
    agent_link._forget_cache()


def test_the_check_in_name_gets_the_published_port(client, monkeypatch):
    monkeypatch.setenv("CHECKIN_ADDRESS", "checkin.lan")
    monkeypatch.setattr(agent_link, "all_agents", lambda: [
        {"connected": True, "report": {"lan_url": "https://10.20.0.5:8443",
                                       "front_door_ports": {"https": 8443, "http": 8080}}}])
    with client.application.app_context():
        url = seat_walk.agent_url()
    assert url == "http://checkin.lan:8080"                        # the check-in name is plain HTTP
    # On the scheme's own port, or with a port already named, nothing is added.
    assert seat_walk._with_port("https://checkin.lan", {"https": 443}) == "https://checkin.lan"
    assert seat_walk._with_port("https://checkin.lan:9443", {"https": 8443}) == "https://checkin.lan:9443"
    assert seat_walk._with_port("http://checkin.lan/x", {"http": 8080}) == "http://checkin.lan:8080/x"


def test_the_agent_reports_its_ports_and_only_sane_ones(client):
    a = enrol(client)
    agent_link.tunnel.report(a["id"], {"up_seconds": 5, "front_door_ports": {"https": 8443, "http": "80; rm", "x": 1}})
    assert agent_link.tunnel._reports[a["id"]]["front_door_ports"] == {"https": 8443}
    agent_link.tunnel.report(a["id"], {"up_seconds": 6, "front_door_ports": {"https": 70000}})
    assert "front_door_ports" not in agent_link.tunnel._reports[a["id"]]


def test_reached_in_the_hall_at_wins(client, monkeypatch):
    a = enrol(client)
    monkeypatch.setenv("CHECKIN_ADDRESS", "checkin.lan")
    bad = client.patch(f"/api/agents/{a['id']}/settings", json={"settings": {"hall_url": "javascript:alert(1)"}})
    assert bad.status_code == 400
    ok = client.patch(f"/api/agents/{a['id']}/settings", json={"settings": {"hall_url": "https://walk.example.com:8443/"}})
    assert ok.status_code == 200
    monkeypatch.setattr(agent_link, "all_agents", lambda: [{"id": a["id"], "connected": True, "report": {}}])
    with client.application.app_context():
        assert seat_walk.agent_url() == "https://walk.example.com:8443"
    # The hall's own FLOORBIT_AGENT_HALL_URL wins over Floorbit's, as on the agent.
    report = {"settings": {"values": {"hall_url": {"source": "env", "value": "https://door.example.com:9443"}}}}
    monkeypatch.setattr(agent_link, "all_agents", lambda: [{"id": a["id"], "connected": True, "report": report}])
    with client.application.app_context():
        assert seat_walk.agent_url() == "https://door.example.com:9443"
