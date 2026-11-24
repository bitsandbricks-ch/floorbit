"""Dismiss on an incident (issue #887): not a problem, or snoozed for a while."""
import time

from floorbit import incidents
from tests.test_incidents import floor  # noqa: F401  (fixture)


def _new(client):
    return client.post("/api/incidents", json={"seat": "A-1", "title": "Cable cut", "team": "core"}).get_json()


def test_not_a_problem_closes_it_with_the_reason(client, floor):  # noqa: F811
    i = _new(client)
    r = client.patch(f"/api/incidents/{i['id']}", json={"dismiss": "not_a_problem", "note": "Player unplugged it"})
    assert r.status_code == 200, r.get_json()
    done = r.get_json()
    assert done["status"] == "fixed" and done["fixed_at"]
    assert done["dismissed"]["reason"] == "not_a_problem"
    assert done["notes"][-1]["text"] == "Player unplugged it"
    # Reopening forgets the dismissal.
    again = client.patch(f"/api/incidents/{i['id']}", json={"status": "open"}).get_json()
    assert "dismissed" not in again
    assert client.patch(f"/api/incidents/{i['id']}", json={"dismiss": "bored"}).status_code == 400


def test_a_snooze_puts_it_aside_until_it_runs_out(client, floor):  # noqa: F811
    i = _new(client)
    r = client.patch(f"/api/incidents/{i['id']}", json={"snooze": 30}).get_json()
    assert r["status"] == "open" and r["snoozed_until"] > time.time() + 29 * 60
    later = {**r, "created_at": time.time() - 3600}
    assert incidents.snoozed(later, time.time())
    assert not incidents.is_waiting(later, time.time())
    assert incidents.is_waiting(later, r["snoozed_until"] + 1)
    # Taking it ends the snooze; a snooze of 0 does too.
    taken = client.patch(f"/api/incidents/{i['id']}", json={"status": "assigned"}).get_json()
    assert "snoozed_until" not in taken
    client.patch(f"/api/incidents/{i['id']}", json={"snooze": 10})
    assert "snoozed_until" not in client.patch(f"/api/incidents/{i['id']}", json={"snooze": 0}).get_json()


def test_snoozes_are_bounded(client, floor):  # noqa: F811
    i = _new(client)
    for bad in (-1, 24 * 60 + 1, "x"):
        assert client.patch(f"/api/incidents/{i['id']}", json={"snooze": bad}).status_code == 400, bad
    client.patch(f"/api/incidents/{i['id']}", json={"status": "fixed"})
    assert client.patch(f"/api/incidents/{i['id']}", json={"snooze": 5}).status_code == 400
