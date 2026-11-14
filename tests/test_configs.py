"""Switch config backups and diffs (issue #96): on demand with the tech's login, secrets removed."""
import json

import pytest

from floorbit import audit, config_backup, ports

SWITCHES = [{"name": "sw-a-01", "mgmt_ip": "198.51.100.4", "role": "switch"},
            {"name": "sw-a-02", "mgmt_ip": "198.51.100.5", "role": "switch"}]


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    for state in (ports._last, ports._failures, ports._busy, ports._shut if hasattr(ports, "_shut") else set()):
        state.clear()
    monkeypatch.setattr(config_backup, "folder", lambda: str(tmp_path / "configs"))


@pytest.fixture
def demo(client):
    for s in SWITCHES:
        assert client.post("/api/inventory", json=s).status_code in (200, 201)
    client.put("/api/settings/plugins/demo", json={"enabled": True})


def sign_in(app_module, username, role):
    app_module.app.extensions["auth"].users.add(username, "role-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": username, "password": "role-password-1"}).status_code == 302
    return c


def audit_lines():
    try:
        with open(audit.path(), encoding="utf-8") as f:
            return [e for e in (json.loads(line) for line in f) if e["area"] == "configs"]
    except FileNotFoundError:
        return []


def test_secrets_and_noise_are_taken_out():
    clean = config_backup.scrub(
        "Building configuration...\r\nCurrent configuration : 4211 bytes\r\n! Last configuration change at 12:00\r\n"
        "enable secret 9 $9$abc\r\nusername ops privilege 15 secret 9 $9$def\r\nsnmp-server community s3cret RO\r\n"
        "tacacs-server host 192.0.2.5 key 7 0822455D\r\nhostname sw-a-01\r\n")
    assert clean == ("enable secret 9 <removed>\nusername ops privilege 15 secret 9 <removed>\n"
                     "snmp-server community <removed> RO\ntacacs-server host 192.0.2.5 key 7 <removed>\n"
                     "hostname sw-a-01\n")


def test_only_changes_are_kept_and_diffed(tmp_path):
    first, changed = config_backup.save("sw-a-01", "hostname sw-a-01\ninterface Gi1/0/1\n", "kim", now=1000)
    assert changed
    again, changed = config_backup.save("sw-a-01", "! Last configuration change at 13:00\nhostname sw-a-01\n"
                                                   "interface Gi1/0/1\n", "kim", now=2000)
    assert not changed and again["id"] == first["id"]
    config_backup.save("sw-a-01", "hostname sw-a-01\ninterface Gi1/0/1\n shutdown\n", "lee", now=3000)
    d = config_backup.diff("sw-a-01")
    assert (d["added"], d["removed"]) == (1, 0) and "+ shutdown" in d["lines"]
    assert config_backup.overview(["sw-a-01", "sw-a-02"])[0]["changed"] is True
    assert config_backup.overview(["sw-a-02"])[0]["last"] is None
    # A later baseline: nothing changed since.
    latest = config_backup.history("sw-a-01")["copies"][0]["id"]
    assert config_backup.set_baseline("sw-a-01", latest)
    assert config_backup.overview(["sw-a-01"])[0]["changed"] is False


def test_old_copies_go_but_the_baseline_stays(monkeypatch):
    monkeypatch.setenv("CONFIG_KEEP", "3")
    first, _ = config_backup.save("sw-a-01", "v0\n", "kim", now=1000)
    for i in range(1, 6):
        config_backup.save("sw-a-01", f"v{i}\n", "kim", now=1000 + i)
    ids = [c["id"] for c in config_backup.history("sw-a-01")["copies"]]
    assert len(ids) == 3 and first["id"] in ids
    assert config_backup.text("sw-a-01", first["id"]) == "v0\n"


def test_demo_backup_end_to_end_and_audited(client, demo):
    resp = client.post("/api/configs/backup", json={"switches": ["sw-a-01", "sw-a-02"]})
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert all(r["ok"] and r["changed"] for r in body["results"])
    rows = {r["switch"]: r for r in client.get("/api/configs").get_json()["switches"]}
    assert rows["sw-a-01"]["copies"] == 1 and rows["sw-a-01"]["changed"] is False
    cid = rows["sw-a-01"]["last"]["id"]
    text = client.get(f"/api/configs/sw-a-01/{cid}").get_json()["text"]
    assert "description Seat A-1" in text and "demo-read-only" not in text and "<removed>" in text
    assert "Last configuration change" not in text
    # Shut a port through a port action, back up again: the diff shows it.
    assert client.post("/api/ports/shutdown", json={"switch": "sw-a-01", "port": "Gi1/0/3"}).status_code == 200
    client.post("/api/configs/backup", json={"switches": ["sw-a-01"]})
    d = client.get("/api/configs/sw-a-01/diff").get_json()
    assert d["added"] == 1 and " shutdown" in [ln[1:] for ln in d["lines"] if ln.startswith("+")]
    download = client.get(f"/api/configs/sw-a-01/{cid}?download=1")
    assert download.mimetype == "text/plain" and "attachment" in download.headers["Content-Disposition"]
    actions = [(e["action"], e["target"]) for e in audit_lines()]
    assert ("Backed up switch config (changed)", "sw-a-01") in actions
    client.post("/api/ports/enable", json={"switch": "sw-a-01", "port": "Gi1/0/3"})


def test_needs_configs_read(app_module, client, demo):
    tech = sign_in(app_module, "fixer", "tech")
    assert tech.get("/api/configs").status_code == 403
    assert tech.post("/api/configs/backup", json={"switches": ["sw-a-01"]}).status_code == 403
    lead = sign_in(app_module, "boss", "lead")
    assert lead.get("/api/configs").status_code == 200
    assert client.get("/api/configs/sw-a-01/nope").status_code == 404
    assert client.get("/api/configs/sw-a-01/diff").status_code == 404
    assert client.post("/api/configs/sw-a-01/baseline", json={"id": "nope"}).status_code == 404
    assert client.get("/api/configs/..%2Fetc/x").status_code == 404
