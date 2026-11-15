"""Incident board and seat QR helpdesk (issue #27)."""
import time

import pytest

from floorbit import audit, incidents
from floorbit.blueprints import incidents as incidents_bp
from tests.conftest import TEST_USER


def sign_in_as(app_module, username, role, teams=None, password="role-password-1"):
    users = app_module.app.extensions["auth"].users
    users.add(username, password, role=role)
    for team, team_role in (teams or {}).items():
        from auth import teams as team_store
        team_store.set_member(username, team, team_role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": username, "password": password}).status_code == 302
    return c


@pytest.fixture
def floor(client):
    """Block A with seats A-1..A-4 and one switch."""
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 2, "rows": 2})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 20, "y": 20}).get_json()
    return {"switch_id": sw["id"]}


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    incidents_bp._reports.clear()


def help_url(app_module, seat):
    with app_module.app.test_request_context():
        return f"/help/{seat}?k={incidents.signature(seat)}"


# ── Seats and links ────────────────────────────────────────────────────────────

def test_seat_numbers_follow_the_editor(client, floor):
    assert incidents.seat_numbers() == {"A-1", "A-2", "A-3", "A-4"}


def test_help_link_only_works_signed_and_for_real_seats(anon_client, app_module, floor):
    assert anon_client.get(help_url(app_module, "A-1")).status_code == 200
    assert anon_client.get("/help/A-1").status_code == 404
    assert anon_client.get("/help/A-1?k=0000000000000000").status_code == 404
    assert anon_client.get(help_url(app_module, "Z-9")).status_code == 404


def test_attendee_reports_without_an_account(anon_client, client, app_module, floor):
    url = help_url(app_module, "A-1")
    resp = anon_client.post(url, data={"problem": "no-internet"})
    assert resp.status_code == 200 and b"Someone from the team will come" in resp.data
    [incident] = client.get("/api/incidents").get_json()["incidents"]
    assert incident["seat"] == "A-1" and incident["team"] == "access" and incident["source"] == "helpdesk"
    assert incident["reported_by"] is None
    assert incident["snapshot"]["known"] is False      # no monitoring in tests: says so, doesn't fail
    # Asking again counts up instead of filing a second one.
    assert b"asked again" in anon_client.post(url, data={"problem": "no-internet"}).data
    [incident] = client.get("/api/incidents").get_json()["incidents"]
    assert incident["reports"] == 2
    rows, _ = audit.read(area="incidents")
    assert [r["action"] for r in rows[:2]] == ["Reported again from seat", "Reported from seat"]


def test_help_page_speaks_german(anon_client, app_module, floor):
    resp = anon_client.get(help_url(app_module, "A-1"), headers={"Accept-Language": "de-CH,de;q=0.9"})
    assert b"Kein Internet" in resp.data


def test_help_page_is_rate_limited_and_takes_only_known_problems(anon_client, app_module, floor):
    url = help_url(app_module, "A-2")
    assert anon_client.post(url, data={"problem": "free text <b>"}).status_code == 400
    for _ in range(incidents_bp.RATE_LIMIT):
        assert anon_client.post(url, data={"problem": "slow"}).status_code == 200
    assert anon_client.post(url, data={"problem": "slow"}).status_code == 429


def test_report_holds_no_personal_data(client, anon_client, app_module, floor, monkeypatch):
    client.put("/api/seat-map/A-3", json={"ip_address": "192.0.2.33", "nick": "player-three"})

    class Monitoring:
        def resolve_ip(self, ip):
            return {"device_name": "sw-a-01", "port": "Gi1/0/3", "mac": "02:00:00:00:00:33", "ip": ip,
                    "stats": {"state": "errors", "speed_bps": 1e9, "duplex": "full", "error_rate": 2.5}}

        def ip_for_mac(self, mac):
            return None
    from floorbit import sources
    monkeypatch.setattr(sources, "monitoring", lambda: Monitoring())
    anon_client.post(help_url(app_module, "A-3"), data={"problem": "slow"})
    [incident] = client.get("/api/incidents").get_json()["incidents"]
    snap = incident["snapshot"]
    assert snap["known"] and snap["switch"] == "sw-a-01" and snap["port"] == "Gi1/0/3"
    assert snap["link"] == "errors" and snap["mac_seen"] is True
    text = str(incident)
    assert "192.0.2.33" not in text and "02:00:00:00:00:33" not in text and "player-three" not in text


# ── The board ──────────────────────────────────────────────────────────────────

def test_board_needs_incidents_work(anon_client, app_module):
    assert anon_client.get("/api/incidents").status_code == 401
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.get("/api/incidents").status_code == 403
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.get("/api/incidents").status_code == 200


def test_team_role_opens_the_board_for_that_team_only(client, app_module, floor):
    a = client.post("/api/incidents", json={"seat": "A-1", "title": "Cable cut", "team": "core"}).get_json()
    b = client.post("/api/incidents", json={"seat": "A-2", "title": "No power", "team": "electrics"}).get_json()
    # A viewer whose team role is tech in Infra works Infra and its sub-teams (Core), nothing else.
    infra = sign_in_as(app_module, "in1", "viewer", {"infra": "tech"})
    board = {i["id"]: i for i in infra.get("/api/incidents").get_json()["incidents"]}
    assert board[a["id"]]["can_work"] and not board[b["id"]]["can_work"]
    assert infra.patch(f"/api/incidents/{a['id']}", json={"status": "assigned"}).get_json()["assignee"] == "in1"
    assert infra.patch(f"/api/incidents/{b['id']}", json={"status": "fixed"}).status_code == 403


def test_assigning_to_others_and_moving_teams_needs_assign(client, app_module, floor):
    sign_in_as(app_module, "te2", "viewer", {"core": "tech"})
    tech = sign_in_as(app_module, "te1", "viewer", {"core": "tech"})
    i = client.post("/api/incidents", json={"seat": "A-1", "title": "Cable cut", "team": "core"}).get_json()
    assert tech.patch(f"/api/incidents/{i['id']}", json={"assignee": "te2"}).status_code == 403
    assert tech.patch(f"/api/incidents/{i['id']}", json={"team": "electrics"}).status_code == 403
    lead = sign_in_as(app_module, "le1", "lead")
    resp = lead.patch(f"/api/incidents/{i['id']}", json={"assignee": "te2"}).get_json()
    assert resp["assignee"] == "te2" and resp["status"] == "assigned"
    # Moving it to a team te2 doesn't work for drops the assignee.
    resp = lead.patch(f"/api/incidents/{i['id']}", json={"team": "electrics"}).get_json()
    assert resp["team"] == "electrics" and resp["assignee"] is None and resp["status"] == "open"
    # Nobody can be given an incident for a team they don't work.
    assert lead.patch(f"/api/incidents/{i['id']}", json={"assignee": "te2"}).status_code == 400


def test_work_flow_with_notes(client, floor):
    i = client.post("/api/incidents", json={"switch_id": floor["switch_id"], "title": "Switch beeps",
                                            "team": "core", "note": "Fan noise"}).get_json()
    assert i["switch_name"] == "sw-a-01" and i["notes"][0]["text"] == "Fan noise"
    i = client.patch(f"/api/incidents/{i['id']}", json={"status": "fixed", "note": "Swapped the fan"}).get_json()
    assert i["status"] == "fixed" and i["fixed_at"] and len(i["notes"]) == 2
    i = client.patch(f"/api/incidents/{i['id']}", json={"status": "open"}).get_json()
    assert i["status"] == "open" and i["assignee"] is None


@pytest.mark.parametrize("body", [
    {"title": "x"},                                              # neither seat nor switch
    {"seat": "A-1", "switch_id": "x", "title": "x"},
    {"seat": "Z-99", "title": "x"},
    {"switch_id": "nope", "title": "x"},
    {"seat": "A-1", "title": "   "},
    {"seat": "A-1", "title": "x", "team": "nope"},
])
def test_bad_incidents_are_refused(client, floor, body):
    assert client.post("/api/incidents", json=body).status_code == 400


def test_markers_count_open_incidents(client, floor):
    client.post("/api/incidents", json={"seat": "A-1", "title": "a"})
    done = client.post("/api/incidents", json={"seat": "A-2", "title": "b"}).get_json()
    client.patch(f"/api/incidents/{done['id']}", json={"status": "fixed"})
    client.post("/api/incidents", json={"switch_id": floor["switch_id"], "title": "c"})
    assert client.get("/api/incidents/markers").get_json() == {"seats": {"A-1": 1}, "switches": {floor["switch_id"]: 1}}


def test_qr_sheet_needs_assign_and_holds_signed_links(client, app_module, floor):
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.get("/api/helpdesk/qr").status_code == 403
    seats = client.get("/api/helpdesk/qr").get_json()["seats"]
    assert [s["seat"] for s in seats] == ["A-1", "A-2", "A-3", "A-4"]
    assert seats[0]["url"].endswith(help_url(app_module, "A-1")) and seats[0]["image"].startswith("data:image/svg+xml")


def test_board_changes_are_audited(client, floor):
    i = client.post("/api/incidents", json={"seat": "A-1", "title": "Cable cut"}).get_json()
    client.patch(f"/api/incidents/{i['id']}", json={"status": "fixed"})
    rows, _ = audit.read(area="incidents")
    assert [(r["action"], r["target"]) for r in rows] == [("Changed incident", "Cable cut"),
                                                          ("Filed incident", "Cable cut")]


def test_board_shows_the_seat_s_crew_note(client, floor):
    client.post("/api/incidents", json={"seat": "A-2", "title": "No link"})
    client.post("/api/incidents", json={"seat": "A-3", "title": "Slow"})
    client.put("/api/plan/seats/A-2/note", json={"text": "Cable swapped at 14:20"})
    cards = {i["seat"]: i for i in client.get("/api/incidents").get_json()["incidents"]}
    assert cards["A-2"]["seat_note"]["text"] == "Cable swapped at 14:20" and cards["A-2"]["seat_note"]["at"]
    assert cards["A-3"]["seat_note"] is None


def test_attendee_says_it_works_again(anon_client, client, app_module, floor):
    # Issue #372: tags the seat's open reports for the crew; only the crew can mark them fixed.
    url = help_url(app_module, "A-3")
    assert b'name="works"' not in anon_client.get(url).data        # nothing reported, nothing to call off
    anon_client.post(url, data={"problem": "no-internet"})
    assert b'name="works"' in anon_client.get(url).data
    resp = anon_client.post(url, data={"works": "1"})
    assert resp.status_code == 200 and b"we told the team it works again" in resp.data
    (incident,) = [i for i in client.get("/api/incidents").get_json()["incidents"] if i["seat"] == "A-3"]
    assert incident["seat_ok_at"] and incident["status"] == "open"
    page = anon_client.get(url).data.decode()
    assert "You told us it works again" in page and 'name="works"' not in page
    rows, _ = audit.read(area="incidents")
    assert rows[0]["action"] == "Seat says it works again" and rows[0]["target"] == "A-3"
    # Broken again: a new report clears it.
    anon_client.post(url, data={"problem": "no-internet"})
    (incident,) = [i for i in client.get("/api/incidents").get_json()["incidents"] if i["seat"] == "A-3"]
    assert not incident.get("seat_ok_at") and incident["reports"] == 2


def test_a_seat_that_works_again_is_not_waiting(anon_client, app_module, floor):
    # Issue #376: the board's "Waiting" rule, also counted by the handover and the dashboard.
    anon_client.post(help_url(app_module, "A-2"), data={"problem": "slow"})
    with app_module.app.app_context():
        (incident,) = incidents.list_all()
        later = incident["created_at"] + 20 * 60
        assert incidents.is_waiting(incident, later)
        incidents.seat_says_ok("A-2")
        assert not incidents.is_waiting(incidents.get(incident["id"]), later)


def test_the_help_page_says_how_many_reports_are_ahead(anon_client, client, app_module, floor):
    # Issue #378: a count only, from the whole board's open queue.
    now = time.time()
    first = client.post("/api/incidents", json={"seat": "A-1", "title": "Filed first"}).get_json()
    taken = client.post("/api/incidents", json={"seat": "A-2", "title": "Someone has it"}).get_json()
    client.patch(f"/api/incidents/{taken['id']}", json={"assignee": TEST_USER})
    with app_module.app.app_context():
        incidents.stamp(first["id"], created_at=now - 300)
        incidents.stamp(taken["id"], created_at=now - 200)
    url = help_url(app_module, "A-4")
    anon_client.post(url, data={"problem": "slow"})
    page = anon_client.get(url).data.decode()
    assert "One report is ahead of yours." in page and "Filed first" not in page
    client.patch(f"/api/incidents/{first['id']}", json={"assignee": TEST_USER})
    assert "ahead of yours" not in anon_client.get(url).data.decode()


def test_works_again_without_a_report_changes_nothing(anon_client, client, app_module, floor):
    client.post("/api/incidents", json={"seat": "A-4", "title": "Filed by the crew"})
    assert anon_client.post(help_url(app_module, "A-4"), data={"works": "1"}).status_code == 200
    (incident,) = client.get("/api/incidents").get_json()["incidents"]
    assert not incident.get("seat_ok_at")      # the QR link only speaks for the seat's own reports
    assert not [r for r in audit.read(area="incidents")[0] if r["action"] == "Seat says it works again"]


def test_the_help_page_says_where_the_seats_report_stands(anon_client, client, app_module, floor):
    url = help_url(app_module, "A-2")
    assert b'class="report' not in anon_client.get(url).data
    anon_client.post(url, data={"problem": "slow"})
    assert b"Nobody from the team has taken it yet" in anon_client.get(url).data
    (incident,) = [i for i in client.get("/api/incidents").get_json()["incidents"] if i["seat"] == "A-2"]
    client.patch(f"/api/incidents/{incident['id']}", json={"assignee": TEST_USER})
    page = anon_client.get(url).data.decode()
    assert "Someone from the team has your report" in page and TEST_USER not in page   # no names
    # Issue #362: sent by dispatch but not seen yet, the page doesn't promise anyone is on the way.
    with app_module.app.app_context():
        incidents.stamp(incident["id"], dispatched_at=time.time(), taken_at=None)
    page = anon_client.get(url).data.decode()
    assert "sent to a tech nearby" in page and "is on the way" not in page and TEST_USER not in page
    with app_module.app.app_context():
        incidents.stamp(incident["id"], taken_at=time.time())
    assert "is on the way" in anon_client.get(url).data.decode()
    client.patch(f"/api/incidents/{incident['id']}", json={"status": "fixed"})
    assert "Jemand" not in anon_client.get(url).data.decode()
    german = anon_client.get(url, headers={"Accept-Language": "de-CH"}).data.decode()
    assert "Deine Meldung wurde als erledigt markiert" in german
    # Half an hour after the fix the page forgets it.
    with app_module.app.app_context():
        assert incidents.seat_report_state("A-2", now=time.time() + 31 * 60) is None
        assert incidents.seat_report_state("A-3") is None


def test_the_help_page_says_when_the_seat_s_switch_is_down(anon_client, client, app_module, floor, monkeypatch):
    # Issue #384: a known outage, so attendees don't each report it.
    from floorbit import status_page
    monitor = app_module.app.extensions["lal_integrations"]["monitor"]
    watch = app_module.app.extensions["floorbit_attention"]
    monkeypatch.setattr(watch, "port_seats", {("sw-a-01", "Gi1/0/1"): "A-1"}, raising=False)
    monkeypatch.setattr(status_page, "_seats_of", {})
    monkeypatch.setattr(monitor, "last_poll", time.time())
    monkeypatch.setattr(monitor, "statuses", {})
    assert b"has been down" not in anon_client.get(help_url(app_module, "A-1")).data
    monitor.statuses = {floor["switch_id"]: {"status": "offline", "since": time.time() - 12 * 60}}
    page = anon_client.get(help_url(app_module, "A-1")).data.decode()
    assert "has been down for 12 min" in page and "sw-a-01" not in page
    assert 'href="/status"' not in page            # issue #388: only when the status page is public
    assert client.put("/api/settings", json={"public.status_page": True}).status_code == 200
    assert 'href="/status"' in anon_client.get(help_url(app_module, "A-1")).data.decode()
    assert b"has been down" not in anon_client.get(help_url(app_module, "A-2")).data   # its port isn't known
    # Remembered by the status page once the port read no longer has it.
    monkeypatch.setattr(watch, "port_seats", {}, raising=False)
    status_page.learn_seats({("sw-a-01", "Gi1/0/2"): "A-2"})
    assert b"has been down" in anon_client.get(help_url(app_module, "A-2")).data


def test_the_board_says_when_an_incident_s_seat_is_on_a_down_switch(client, app_module, floor, monkeypatch):
    # Issue #386: the crew sees it is part of an outage, not a cable.
    from floorbit import status_page
    monitor = app_module.app.extensions["lal_integrations"]["monitor"]
    watch = app_module.app.extensions["floorbit_attention"]
    monkeypatch.setattr(watch, "port_seats", {("sw-a-01", "Gi1/0/1"): "A-1"}, raising=False)
    monkeypatch.setattr(status_page, "_seats_of", {})
    monkeypatch.setattr(monitor, "last_poll", time.time())
    monkeypatch.setattr(monitor, "statuses", {})
    client.post("/api/incidents", json={"seat": "A-1", "title": "No link"})
    client.post("/api/incidents", json={"seat": "A-2", "title": "Slow"})
    assert all(i["outage"] is None for i in client.get("/api/incidents").get_json()["incidents"])
    since = time.time() - 300
    monitor.statuses = {floor["switch_id"]: {"status": "offline", "since": since}}
    cards = {i["seat"]: i for i in client.get("/api/incidents").get_json()["incidents"]}
    assert cards["A-1"]["outage"] == {"switch": "sw-a-01", "since": since}
    assert cards["A-2"]["outage"] is None


def test_the_board_says_when_the_switch_came_back(client, app_module, floor, monkeypatch):
    # Issue #390: filed during the outage, the switch is back since: maybe fixed already.
    from floorbit import status_page
    monitor = app_module.app.extensions["lal_integrations"]["monitor"]
    watch = app_module.app.extensions["floorbit_attention"]
    monkeypatch.setattr(watch, "port_seats", {("sw-a-01", "Gi1/0/1"): "A-1"}, raising=False)
    monkeypatch.setattr(status_page, "_seats_of", {})
    monkeypatch.setattr(monitor, "last_poll", time.time())
    filed = client.post("/api/incidents", json={"seat": "A-1", "title": "No link"}).get_json()
    sid = floor["switch_id"]
    # Up since before it was filed, or up since a restart: nothing to say.
    monkeypatch.setattr(monitor, "statuses", {sid: {"status": "online", "since": filed["created_at"] - 60,
                                                    "previous": "offline"}})
    assert client.get("/api/incidents").get_json()["incidents"][0]["back_up"] is None
    monitor.statuses = {sid: {"status": "online", "since": filed["created_at"] + 60}}
    assert client.get("/api/incidents").get_json()["incidents"][0]["back_up"] is None
    monitor.statuses = {sid: {"status": "online", "since": filed["created_at"] + 60, "previous": "offline"}}
    card = client.get("/api/incidents").get_json()["incidents"][0]
    assert card["back_up"] == {"switch": "sw-a-01", "since": filed["created_at"] + 60} and card["outage"] is None


def test_the_help_page_asks_when_the_switch_came_back(anon_client, app_module, floor, monkeypatch):
    # Issue #392: reported during the outage, the switch is back: ask before a tech walks over.
    from floorbit import status_page
    monitor = app_module.app.extensions["lal_integrations"]["monitor"]
    watch = app_module.app.extensions["floorbit_attention"]
    monkeypatch.setattr(watch, "port_seats", {("sw-a-01", "Gi1/0/1"): "A-1"}, raising=False)
    monkeypatch.setattr(status_page, "_seats_of", {})
    monkeypatch.setattr(monitor, "last_poll", time.time())
    sid = floor["switch_id"]
    back = {sid: {"status": "online", "since": time.time() - 3 * 60, "previous": "offline"}}
    monkeypatch.setattr(monitor, "statuses", back)
    url = help_url(app_module, "A-1")
    assert b"has been back" not in anon_client.get(url).data          # nothing reported
    with app_module.app.app_context():
        incident, _ = incidents.report_from_seat("A-1", "no-internet", {})
        incidents.stamp(incident["id"], created_at=time.time() - 10 * 60)
    page = anon_client.get(url).data.decode()
    assert "has been back for 3 min" in page and "sw-a-01" not in page and 'name="works"' in page
    assert "wieder da" in anon_client.get(url, headers={"Accept-Language": "de"}).data.decode()
    # Back since before the report: the report is about something else.
    monitor.statuses = {sid: {**back[sid], "since": time.time() - 20 * 60}}
    assert b"has been back" not in anon_client.get(url).data
    # Once the seat said it works again, there is nothing left to ask.
    monitor.statuses = back
    anon_client.post(url, data={"works": "1"})
    assert b"has been back" not in anon_client.get(url).data


# ── CSV export (issue #418) ────────────────────────────────────────────────────
def test_csv_export_for_the_debrief(client, anon_client, app_module, floor):
    import csv
    import io
    a = client.post("/api/incidents", json={"seat": "A-1", "title": "=HYPERLINK(\"x\")", "team": "core",
                                            "note": "Swapped the cable for Kim"}).get_json()
    client.patch(f"/api/incidents/{a['id']}", json={"status": "assigned"})
    client.patch(f"/api/incidents/{a['id']}", json={"status": "fixed"})
    client.post("/api/incidents", json={"switch_id": floor["switch_id"], "title": "Fan noise"})
    resp = client.get("/api/incidents.csv?tz=-60")
    assert resp.status_code == 200 and resp.mimetype == "text/csv"
    assert resp.headers["Content-Disposition"].startswith('attachment; filename="incidents-')
    text = resp.get_data(as_text=True)
    assert text.startswith("﻿")
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    assert [r["where"] for r in rows] == ["seat A-1", "sw-a-01"]   # oldest first
    first = rows[0]
    assert first["title"] == "'=HYPERLINK(\"x\")"   # never a formula in a spreadsheet
    assert first["status"] == "fixed" and first["fixed"] and first["minutes_to_fix"] == "0"
    assert first["team"] and first["notes"] == "1" and "Kim" not in text   # note texts stay out
    assert first["assignee"] == TEST_USER and rows[1]["fixed"] == ""
    entries, _ = audit.read(area="incidents")
    assert any(e["action"] == "Downloaded the incident list" for e in entries)

    assert anon_client.get("/api/incidents.csv").status_code == 401
    assert sign_in_as(app_module, "vi2", "viewer").get("/api/incidents.csv").status_code == 403
    assert client.get("/api/incidents.csv?tz=abc").status_code == 200


def test_csv_times_follow_the_browser_clock():
    rows = incidents_bp.csv_rows([{"id": "x", "seat": "A-1", "title": "t", "status": "open", "created_at": 3600}],
                                 {}, tz=-120)
    assert rows[1][1] == "1970-01-01 03:00"
