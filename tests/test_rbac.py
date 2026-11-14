"""Roles, permissions and teams (issue #41)."""
import json

import pytest

from auth import roles, teams
from floorbit import audit


def sign_in_as(app_module, username, role, password="role-password-1"):
    app_module.app.extensions["auth"].users.add(username, password, role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": username, "password": password}).status_code == 302
    return c


# ── Roles ──────────────────────────────────────────────────────────────────────

def test_old_editor_accounts_are_leads_and_accounts_without_a_role_are_admins():
    assert roles.of({"role": "editor"}) == "lead"
    assert roles.of({}) == "admin"
    assert roles.of({"role": "gone-role"}) == "viewer"    # a deleted custom role grants least
    assert roles.validate("Editor") == "lead"


def test_admin_has_every_permission_and_viewer_only_looks():
    assert roles.permissions_of("admin") == set(roles.PERMISSIONS)
    assert roles.permissions_of("viewer") == {"floorplan.view"}
    assert roles.permissions_of("kiosk") == {"floorplan.view"}


def test_custom_role_round_trip(client):
    body = {"label": "Helpdesk", "permissions": ["floorplan.view", "seats.view"]}
    resp = client.put("/api/roles/helpdesk", json=body)
    assert resp.status_code == 200, resp.data
    listed = {r["id"]: r for r in client.get("/api/roles").get_json()["roles"]}
    assert listed["helpdesk"]["permissions"] == ["floorplan.view", "seats.view"]
    assert listed["helpdesk"]["builtin"] is False
    assert client.delete("/api/roles/helpdesk").status_code == 200
    assert "helpdesk" not in {r["id"] for r in client.get("/api/roles").get_json()["roles"]}


@pytest.mark.parametrize("role_id, body", [
    ("admin", {"label": "Admin", "permissions": []}),             # built-in
    ("editor", {"label": "Editor", "permissions": []}),           # old alias
    ("Bad ID", {"label": "x", "permissions": []}),
    ("helpdesk", {"label": "Helpdesk", "permissions": ["root.everything"]}),
    ("helpdesk", {"label": "", "permissions": []}),
    ("helpdesk", {"label": "Helpdesk", "permissions": "seats.view"}),
])
def test_bad_roles_are_refused(client, role_id, body):
    assert client.put(f"/api/roles/{role_id}", json=body).status_code == 400


def test_a_role_in_use_cannot_be_deleted(client, app_module):
    client.put("/api/roles/helpdesk", json={"label": "Helpdesk", "permissions": ["floorplan.view"]})
    app_module.app.extensions["auth"].users.add("hd1", "helpdesk-password-1", role="helpdesk")
    resp = client.delete("/api/roles/helpdesk")
    assert resp.status_code == 400 and "hd1" in resp.get_json()["error"]


def test_nobody_can_lock_everyone_out_of_account_management(client, app_module):
    # The only manager holds a custom role; taking accounts.manage off it would lock everyone out.
    client.put("/api/roles/boss", json={"label": "Boss", "permissions": list(roles.PERMISSIONS)})
    users = app_module.app.extensions["auth"].users
    with open(users.path) as f:
        data = json.load(f)
    for u in data["auth_users"].values():
        u["role"] = "boss"
    with open(users.path, "w") as f:
        json.dump(data, f)
    assert client.put("/api/roles/boss", json={"label": "Boss", "permissions": ["floorplan.view"]}).status_code == 400


def test_custom_role_permissions_apply_to_requests(client, app_module):
    perms = ["floorplan.view", "seats.view", "seats.edit"]
    client.put("/api/roles/mapper", json={"label": "Mapper", "permissions": perms})
    mapper = sign_in_as(app_module, "map1", "mapper")
    assert mapper.get("/api/seat-map").status_code == 200
    assert mapper.post("/api/switches", json={"name": "sw-x", "x": 1, "y": 1}).status_code == 403


# ── The request guard ──────────────────────────────────────────────────────────

def test_tech_sees_seats_but_changes_nothing_on_them(app_module):
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.get("/api/seat-map").status_code == 200
    assert tech.get("/api/seats/info").status_code == 200
    assert tech.put("/api/seat-map/A-1", json={"ip_address": "192.0.2.10"}).status_code == 403
    assert tech.post("/api/switches", json={"name": "sw-x", "x": 1, "y": 1}).status_code == 403
    assert tech.get("/api/settings/audit").status_code == 403


def test_viewers_and_kiosks_never_see_personal_seat_data(app_module):
    for role in ("viewer", "kiosk"):
        c = sign_in_as(app_module, f"{role}1", role)
        assert c.get("/api/seats/info").status_code == 403
        assert c.get("/api/seat-map").status_code == 403
        assert c.get("/api/checkins").status_code == 403
        assert c.get("/api/seats/occupancy").status_code == 200
        assert c.get("/api/switches").status_code == 200
        assert c.post("/api/switches", json={"name": "sw-x", "x": 1, "y": 1}).status_code == 403


def test_occupancy_says_taken_and_nothing_else(client, anon_client):
    client.put("/api/seat-map/A-1", json={"ip_address": "192.0.2.10", "username": "nick"})
    body = anon_client.get("/api/seats/occupancy").get_json()
    assert list(body) == ["taken"] and all(isinstance(s, str) for s in body["taken"])
    assert "192.0.2.10" not in json.dumps(body) and "nick" not in json.dumps(body)


def test_forbidden_answer_names_the_permission(app_module):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    body = viewer.post("/api/switches", json={"name": "sw-x", "x": 1, "y": 1}).get_json()
    assert body["permission_needed"] == "floorplan.edit"


def test_unmatched_routes_are_closed_for_writes():
    assert roles.needed_for("/api/something-new", "POST") == "settings.manage"
    assert roles.needed_for("/api/something-new", "GET") == "floorplan.view"
    assert roles.needed_for("/api/teams/infra/members/ana", "PUT") == "accounts.manage"


def test_every_write_route_has_a_deliberate_permission(app_module):
    """A write route that falls through to the admin default must be one we meant to keep admin-only."""
    admin_on_purpose = ("/api/settings", "/api/integrations", "/api/demo", "/api/cache", "/api/plugins",
                        "/api/users", "/api/roles", "/api/teams", "/logout", "/login", "/auth/",
                        "/api/checkin", "/help/",   # public pages with their own checks (check-in, helpdesk)
                        "/api/setup",              # first-run setup: admins, or the setup code
                        "/api/stats/peak/reset")   # starting the event's bandwidth peak again
    loose = []
    for rule in app_module.app.url_map.iter_rules():
        writes = (rule.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}
        path = rule.rule.replace("<", "x").replace(">", "")
        if writes and roles.needed_for(path, next(iter(writes))) == "settings.manage" \
                and not path.startswith(admin_on_purpose):
            loose.append(rule.rule)
    assert loose == [], f"Give these a rule in auth/roles.py RULES, or add them here: {loose}"


# ── Teams ──────────────────────────────────────────────────────────────────────

def test_new_installs_start_with_the_default_teams(client):
    names = [t["name"] for t in client.get("/api/teams").get_json()["teams"]]
    assert {"Infra", "Core", "Access", "Wi-Fi", "Operations", "Electrics"} <= set(names)
    tree = {t["id"]: t for t in client.get("/api/teams").get_json()["teams"]}
    assert tree["core"]["parent"] == "infra" and tree["core"]["depth"] == 1


def test_team_crud_and_tree_rules(client):
    tid = client.post("/api/teams", json={"name": "Stage", "parent": "electrics"}).get_json()["id"]
    assert client.patch(f"/api/teams/{tid}", json={"name": "Stage power"}).status_code == 200
    # A team cannot sit inside itself or its own sub-team.
    assert client.patch("/api/teams/electrics", json={"parent": tid}).status_code == 400
    assert client.post("/api/teams", json={"name": "<script>"}).status_code == 400
    assert client.post("/api/teams", json={"name": "x", "parent": "nope"}).status_code == 400
    # Not while it has sub-teams.
    assert client.delete("/api/teams/electrics").status_code == 400
    assert client.delete(f"/api/teams/{tid}").status_code == 200
    assert client.delete("/api/teams/electrics").status_code == 200


def test_teams_go_at_most_five_levels_deep(client):
    parent = None
    for depth in range(teams.MAX_DEPTH):
        parent = client.post("/api/teams", json={"name": f"L{depth}", "parent": parent}).get_json()["id"]
    assert client.post("/api/teams", json={"name": "too deep", "parent": parent}).status_code == 400


def test_team_roles_count_for_sub_teams_only(client, app_module):
    app_module.app.extensions["auth"].users.add("ana", "ana-password-1", role="viewer")
    assert client.put("/api/teams/infra/members/ana", json={"role": "lead"}).status_code == 200
    ana = app_module.app.extensions["auth"].users.get("ana")
    assert "incidents.assign" in teams.team_permissions(ana, "wifi")        # below Infra
    assert "incidents.assign" not in teams.team_permissions(ana, "electrics")
    assert teams.teams_of(ana) == {"infra", "core", "access", "wifi"}
    # The account's own role still decides everything outside teams.
    assert not roles.can(ana, "floorplan.edit")
    members = {t["id"]: t["members"] for t in client.get("/api/teams").get_json()["teams"]}
    assert members["infra"] == [{"username": "ana", "role": "lead", "role_label": "Lead"}]
    assert client.delete("/api/teams/infra/members/ana").status_code == 200
    assert client.put("/api/teams/infra/members/ana", json={}).status_code == 400
    assert client.put("/api/teams/infra/members/nobody", json={"role": "tech"}).status_code == 400


def test_teams_need_account_management(app_module):
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.get("/api/teams").status_code == 403
    assert lead.post("/api/teams", json={"name": "Mine"}).status_code == 403
    assert lead.put("/api/roles/mine", json={"label": "Mine", "permissions": []}).status_code == 403


def test_role_and_team_changes_are_audited(client, app_module):
    app_module.app.extensions["auth"].users.add("ana", "ana-password-1", role="tech")
    client.put("/api/roles/helpdesk", json={"label": "Helpdesk", "permissions": ["floorplan.view"]})
    client.post("/api/teams", json={"name": "Stage"})
    client.put("/api/teams/core/members/ana", json={"role": "tech"})
    rows, _ = audit.read(area="accounts")
    assert [(r["action"], r["target"]) for r in rows][:3] == [
        ("Changed team member", "ana in core"), ("Added team", "Stage"), ("Saved role", "Helpdesk")]
