"""Incident board and seat QR helpdesk (issue #27)."""
import pytest

from floorbit import audit, incidents
from floorbit.blueprints import incidents as incidents_bp


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
