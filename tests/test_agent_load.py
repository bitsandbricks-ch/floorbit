"""Every agent's work over the last hour in one answer: the sparklines on the Local agents list (#1463)."""
import time

from floorbit import agent_history, agent_link
from tests.test_agent import _telemetry_report, enrol


def test_add_up_sums_points_and_syslog_by_time():
    got = agent_history.add_up({"points": [[60, 100.0], [120, 50.0]], "syslog": [[120, 25.0], [180, 5.0]],
                                "sent": [[60, 999.0]]})
    assert got == {"load": [[60, 100.0], [120, 75.0], [180, 5.0]], "syslog": 5.0}
    assert agent_history.add_up({}) == {"load": [], "syslog": None}


def test_load_for_every_agent_in_one_answer(client, anon_client):
    made = enrol(client)
    other = enrol(client, "Hall 3")
    t0 = (time.time() // 60) * 60 - 600
    agent_link.tunnel.report(made["id"], _telemetry_report(t0, 0, 0), now=t0)
    agent_link.tunnel.report(made["id"], _telemetry_report(t0 + 60, 1200, 30), now=t0 + 60)
    got = client.get("/api/agents/load").get_json()
    assert got["hours"] == 1
    assert [v for _, v in got["agents"][made["id"]]["load"]] == [1200.0]
    assert got["agents"][other["id"]] == {"load": [], "syslog": None}
    assert anon_client.get("/api/agents/load").status_code in (401, 403)
