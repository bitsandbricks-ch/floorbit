"""VictoriaLogs as a logs plugin: every syslog line sent as JSON lines, LogsQL searches. Fake API."""
import json

import pytest
import requests

from floorbit import syslog

NOW = 1_794_650_400.0


class Answer:
    def __init__(self, text="", status=200):
        self.status_code = status
        self.text = text


@pytest.fixture
def vlogs(client, app_module, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        calls.append({"method": method, "url": url, "headers": dict(self.headers), **kw})
        if self.headers.get("AccountID") != "7" or self.headers.get("ProjectID") != "0":
            return Answer("", 401)
        if url.endswith("/insert/jsonline"):
            return Answer("")
        if url.endswith("/select/logsql/query"):
            if kw["params"]["query"] == "device:(":
                return Answer("cannot parse query [device:(]: missing ')'", 400)
            rows = [{"_time": f"2026-11-14T09:59:5{9 - i}.123456789Z", "_msg": f"line {i}", "device": "sw-b-01",
                     "severity": "warning", "program": "%PM-4-ERR_DISABLE", "port": "gi1/0/3", "seat": "B-3"}
                    for i in range(3)]
            rows.reverse()   # VictoriaLogs doesn't promise an order
            return Answer("\n".join(json.dumps(r) for r in rows) + "\n")
        return Answer("", 404)

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={"plugin.victorialogs.url": "https://logs.example.com",
                                      "plugin.victorialogs.account": "7", "plugin.victorialogs.event_label": "summer"})
    assert client.put("/api/settings/plugins/victorialogs", json={"enabled": True}).status_code == 200
    return calls


@pytest.fixture
def receiver(app_module, tmp_path):
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r.registry = app_module.app.extensions["floorbit_plugins"]
    return r


def _pushes(calls):
    return [c for c in calls if c["url"].endswith("/insert/jsonline")]


def test_lines_are_sent_once_as_json_lines(vlogs, receiver):
    receiver.receive(b"<14>before the plugin saw anything", "192.0.2.9", now=NOW, check=False)
    receiver.forward_once(now=NOW)        # starts at the newest line: no backlog from before
    assert not _pushes(vlogs)
    receiver.receive(b"<188>%PM-4-ERR_DISABLE: putting Gi1/0/3 in err-disable state", "198.51.100.11", now=NOW + 1,
                     check=False, device="sw-b-01")
    receiver.receive(b"<14>dhcpd: DHCPACK", "192.0.2.9", now=NOW + 2, check=False, device="dhcp-01")
    receiver.forward_once(now=NOW + 3)
    pushes = _pushes(vlogs)
    assert len(pushes) == 1
    assert pushes[0]["params"] == {"_stream_fields": "job,device", "_msg_field": "_msg", "_time_field": "_time"}
    rows = [json.loads(r) for r in pushes[0]["data"].decode().splitlines()]
    assert [r["device"] for r in rows] == ["sw-b-01", "dhcp-01"]
    err = rows[0]
    assert err["severity"] == "warning" and err["event"] == "summer" and err["job"] == "floorbit"
    assert err["port"] == "gi1/0/3" and "err-disable" in err["_msg"]
    assert err["_time"].startswith("2026-") and err["_time"].endswith("Z")
    receiver.forward_once(now=NOW + 4)    # nothing new: nothing sent
    assert len(_pushes(vlogs)) == 1
    assert receiver.status()["stores"] == [{"id": "victorialogs", "name": "VictoriaLogs", "at": NOW + 3, "sent": 2,
                                            "error": None}]


def test_a_failed_push_is_sent_again(client, vlogs, receiver):
    receiver.forward_once(now=NOW)
    client.put("/api/settings", json={"plugin.victorialogs.account": "8"})
    receiver.receive(b"<14>one", "192.0.2.9", now=NOW + 1, check=False)
    receiver.forward_once(now=NOW + 1)
    assert receiver.status()["stores"][0]["error"] == "VictoriaLogs refused the username or password."
    client.put("/api/settings", json={"plugin.victorialogs.account": "7:0"})
    receiver.forward_once(now=NOW + 2)
    last = _pushes(vlogs)[-1]
    assert json.loads(last["data"].decode().splitlines()[0])["_msg"] == "one"
    assert receiver.status()["stores"][0]["error"] is None


def test_search_with_logsql(client, vlogs):
    body = client.get("/api/logs").get_json()
    assert "plugin:victorialogs" in body["status"]["sources"]
    body = client.get("/api/logs?source=plugin:victorialogs&q=device:sw-b-01&hours=6").get_json()
    assert [ln["message"] for ln in body["lines"]] == ["line 0", "line 1", "line 2"]   # newest first
    first = body["lines"][0]
    assert first["seat"] == "B-3" and first["device"] == "sw-b-01" and first["program"] == "%PM-4-ERR_DISABLE"
    query = [c for c in vlogs if c["url"].endswith("/select/logsql/query")][-1]["params"]
    assert query["query"] == "device:sw-b-01" and int(query["end"]) - int(query["start"]) == 6 * 3600
    everything = client.get("/api/logs?source=plugin:victorialogs").get_json()
    assert len(everything["lines"]) == 3
    assert [c for c in vlogs if c["url"].endswith("/select/logsql/query")][-1]["params"]["query"] == "*"
    bad = client.get("/api/logs?source=plugin:victorialogs&q=device:(").get_json()
    assert bad["lines"] == [] and "cannot parse" in bad["status"]["query_error"]


def test_the_connection_test(client, vlogs):
    assert client.post("/api/settings/plugins/victorialogs/test").get_json()["ok"] is True


def test_the_old_environment_variable_is_gone(client, monkeypatch):
    monkeypatch.setenv("FLOORBIT_VICTORIALOGS_URL", "http://victorialogs:9428")
    from floorbit.telemetry import storage
    assert "logs" not in storage.storage().status()
