"""One log viewer (issue #93): Floorbit's own log and the audit log next to the syslog."""
import io

from floorbit import app_log


def test_lines_get_a_program_and_a_level():
    log = app_log.AppLog()
    assert log.add("[syslog] could not prune: disk full")["severity"] == "err"
    line = log.add("[demo] laid out 96 seats")
    assert line["program"] == "demo" and line["message"] == "laid out 96 seats" and line["severity"] == "info"
    assert log.add("[netbox] request timed out, retrying")["severity"] == "warning"
    assert log.add("plain text", stream="stderr")["severity"] == "notice"
    assert log.add("   ") is None
    assert log.add('127.0.0.1 - - [14/Nov/2026 10:00:00] "GET /api/problems HTTP/1.1" 200 -') is None


def test_search():
    log = app_log.AppLog()
    for text in ("[a] one", "[b] could not two", "[a] three"):
        log.add(text)
    assert [ln["message"] for ln in log.search()] == ["three", "could not two", "one"]
    assert [ln["message"] for ln in log.search(q="a three")] == ["three"]
    assert [ln["message"] for ln in log.search(severity="err")] == ["could not two"]
    assert [ln["id"] for ln in log.search(before=3, limit=1)] == [2]
    assert log.search(device="sw-a-01") == []


def test_the_tee_keeps_printing_and_joins_pieces():
    log = app_log.AppLog()
    inner = io.StringIO()
    tee = app_log._Tee(inner, log, "stdout")
    print("[x] hello", file=tee)
    tee.write("[y] in ")
    tee.write("pieces\nand [z] half")
    assert inner.getvalue() == "[x] hello\n[y] in pieces\nand [z] half"
    assert [ln["message"] for ln in log.lines] == ["hello", "in pieces"]


def test_api_sources_need_audit_read(client, app_module, monkeypatch):
    log = app_module.app.extensions["floorbit_app_log"]
    monkeypatch.setattr(log, "lines", app_log.deque(maxlen=100))
    log.add("[syslog] could not prune: disk full")
    body = client.get("/api/logs?source=app").get_json()
    assert body["lines"][0]["message"] == "could not prune: disk full"
    assert body["status"]["sources"] == ["syslog", "app", "audit"] and body["status"]["source"] == "app"
    # An admin change lands in the audit log, and reads back as a line.
    assert client.put("/api/settings/features", json={"replay": False}).status_code == 200
    audit = client.get("/api/logs?source=audit").get_json()["lines"]
    assert audit and audit[0]["program"] == "settings" and audit[0]["severity"] == "notice"
    assert client.get("/api/logs?source=audit&q=nothing-like-this").get_json()["lines"] == []
    assert client.get("/api/logs?source=disk").status_code == 400
    # A tech may read the syslog but not these two.
    app_module.app.extensions["auth"].users.add("tech-one", "tech-password-1", role="tech")
    tech = app_module.app.test_client()
    tech.post("/login", data={"username": "tech-one", "password": "tech-password-1"})
    assert tech.get("/api/logs").get_json()["status"]["sources"] == ["syslog"]
    assert tech.get("/api/logs?source=audit").status_code == 403
    assert tech.get("/api/logs?source=app").status_code == 403
