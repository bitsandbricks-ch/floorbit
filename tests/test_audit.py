"""Audit log: changes and sign-ins are recorded, values never are."""
import csv
import io

from conftest import TEST_PASSWORD, TEST_USER

from floorbit import audit


def entries(client, **params):
    return client.get("/api/settings/audit", query_string=params).get_json()["entries"]


def test_changes_are_logged_with_who_and_what(client):
    sw = client.post("/api/switches", json={"name": "sw-demo-01", "x": 10, "y": 20}).get_json()
    client.put(f"/api/switches/{sw['id']}", json={"x": 15, "y": 25})
    client.delete(f"/api/switches/{sw['id']}")

    rows = entries(client, area="floor plan")
    assert [r["action"] for r in rows] == ["Deleted switch", "Changed switch", "Added switch"]
    assert all(r["user"] == TEST_USER for r in rows)
    assert rows[2]["target"] == "sw-demo-01"
    assert rows[1]["fields"] == ["x", "y"]


def test_settings_log_names_fields_never_values(client):
    client.put("/api/settings", json={"netbox.token": "secret-token-123", "theme.preset": "ops"})
    row = entries(client, area="settings")[0]
    assert row["action"] == "Changed settings" and row["fields"] == ["netbox.token", "theme.preset"]
    with open(audit.path()) as f:
        assert "secret-token-123" not in f.read()


def test_sign_ins_and_failures_are_logged(anon_client, client):
    anon_client.post("/login", data={"username": TEST_USER, "password": "wrong-password"})
    anon_client.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD})
    anon_client.post("/logout")
    rows = entries(client, area="sign-in")
    # newest first; the `client` fixture's own sign-in is the oldest
    assert [r["action"] for r in rows][:3] == ["Signed out", "Signed in", "Sign-in failed"]
    assert rows[2]["ok"] is False and rows[2]["user"] == TEST_USER
    with open(audit.path()) as f:
        assert "wrong-password" not in f.read()


def test_reads_and_refused_requests_are_not_logged(anon_client, client):
    before = len(entries(client, limit=1000))
    client.get("/api/switches")
    anon_client.post("/api/switches", json={"name": "nope", "x": 1, "y": 1})   # 401
    assert len(entries(client, limit=1000)) == before


def test_filters_paging_and_csv(client):
    for i in range(3):
        client.post("/api/switches", json={"name": f"=sw-{i}", "x": i, "y": i})
    body = client.get("/api/settings/audit?area=floor plan&limit=2").get_json()
    assert body["total"] == 3 and len(body["entries"]) == 2
    assert entries(client, q="=sw-1")[0]["target"] == "=sw-1"
    assert entries(client, user="someone-else") == []
    assert client.get("/api/settings/audit?area=nope").status_code == 400

    resp = client.get("/api/settings/audit.csv?area=floor plan")
    assert resp.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8-sig"))))
    assert len(rows) == 3 and rows[0]["target"] == "'=sw-2"   # no spreadsheet formulas


def test_audit_log_needs_audit_read(anon_client, client, app_module):
    """Admins and leads (the old editors) read it; viewers and techs don't (issue #41)."""
    assert anon_client.get("/api/settings/audit").status_code == 401
    users = app_module.app.extensions["auth"].users
    users.add("vi", "viewer-password-1", role="viewer")
    users.add("ed", "editor-password-1", role="editor")
    viewer, lead = app_module.app.test_client(), app_module.app.test_client()
    viewer.post("/login", data={"username": "vi", "password": "viewer-password-1"})
    lead.post("/login", data={"username": "ed", "password": "editor-password-1"})
    assert viewer.get("/api/settings/audit").status_code == 403
    assert viewer.get("/settings/audit").status_code == 403
    assert lead.get("/api/settings/audit").status_code == 200
    # The rest of /settings stays admin-only.
    assert lead.get("/api/settings").status_code == 403
    assert b"Audit log" in client.get("/settings/audit").data


def test_log_is_trimmed_when_it_grows(client, monkeypatch):
    monkeypatch.setattr(audit, "MAX_BYTES", 2000)
    for i in range(60):
        audit.record("floor plan", "Added switch", user="demo", target=f"sw-{i}")
    rows, total = audit.read(limit=1000)
    assert total < 60 and rows[0]["target"] == "sw-59"


def test_account_changes_name_the_account(client):
    client.post("/api/users", json={"username": "helper1", "password": "helper-password-1", "role": "editor"})
    client.patch("/api/users/helper1", json={"role": "viewer", "password": "another-password-1"})
    rows = entries(client, area="accounts")
    assert [(r["action"], r["target"]) for r in rows] == [("Changed account", "helper1"), ("Added account", "helper1")]
    assert rows[0]["fields"] == ["password", "role"]
    with open(audit.path()) as f:
        assert "another-password-1" not in f.read()
