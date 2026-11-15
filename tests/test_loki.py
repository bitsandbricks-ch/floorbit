"""Grafana Loki as a logs plugin (issue #93): every syslog line pushed, LogQL searches. Fake API."""
import json

import pytest
import requests

from floorbit import syslog

NOW = 1_794_650_400.0


class Answer:
    def __init__(self, body=None, status=200, text=""):
        self.status_code = status
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("not JSON")
        return self._body


@pytest.fixture
def loki(client, app_module, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        calls.append({"method": method, "url": url, "headers": dict(self.headers), **kw})
        if self.headers.get("X-Scope-OrgID") != "hall":
            return Answer({}, 401)
        if url.endswith("/loki/api/v1/push"):
            return Answer(None, 204)
        if url.endswith("/loki/api/v1/labels"):
            return Answer({"status": "success", "data": ["job"]})
        if url.endswith("/loki/api/v1/query_range"):
            if "|=" in kw["params"]["query"] and '"' not in kw["params"]["query"]:
                return Answer(None, 400, "parse error at line 1, col 14")
            stream = {"job": "floorbit", "device": "sw-b-01", "severity": "warning"}
            values = [[str(int((NOW - i) * 1e9)), json.dumps({"program": "%PM-4-ERR_DISABLE", "message": f"line {i}",
                                                                "port": "gi1/0/3", "seat": "B-3"})]
                      for i in range(3)]
            return Answer({"status": "success", "data": {"resultType": "streams",
                                                         "result": [{"stream": stream, "values": values}]}})
        return Answer({}, 404)

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={"plugin.loki.url": "https://loki.example.com", "plugin.loki.tenant": "hall",
                                      "plugin.loki.event_label": "summer lan"})
    assert client.put("/api/settings/plugins/loki", json={"enabled": True}).status_code == 200
    return calls


@pytest.fixture
def receiver(app_module, monkeypatch, tmp_path):
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r.registry = app_module.app.extensions["floorbit_plugins"]
    return r


def test_lines_are_pushed_once_with_few_labels(loki, receiver):
    receiver.receive(b"<14>before the plugin saw anything", "192.0.2.9", now=NOW, check=False)
    receiver.forward_once(now=NOW)        # starts at the newest line: no backlog from before
    assert not [c for c in loki if c["url"].endswith("/push")]
    receiver.receive(b"<188>%PM-4-ERR_DISABLE: putting Gi1/0/3 in err-disable state", "198.51.100.11", now=NOW + 1,
                     check=False, device="sw-b-01")
    receiver.receive(b"<14>dhcpd: DHCPACK", "192.0.2.9", now=NOW + 2, check=False, device="dhcp-01")
    receiver.forward_once(now=NOW + 3)
    pushes = [c for c in loki if c["url"].endswith("/push")]
    assert len(pushes) == 1
    streams = pushes[0]["json"]["streams"]
    labels = sorted(tuple(sorted(s["stream"])) for s in streams)
    assert labels == [("device", "event", "job", "severity", "source")] * 2
    err = next(s for s in streams if s["stream"]["device"] == "sw-b-01")
    assert err["stream"]["event"] == "summer_lan" and err["stream"]["severity"] == "warning"
    ns, text = err["values"][0]
    assert ns == str(int((NOW + 1) * 1e9)) and json.loads(text)["port"] == "gi1/0/3"
    receiver.forward_once(now=NOW + 4)    # nothing new: nothing sent
    assert len([c for c in loki if c["url"].endswith("/push")]) == 1
    assert receiver.status()["stores"] == [{"id": "loki", "name": "Grafana Loki", "at": NOW + 3, "sent": 2,
                                            "error": None}]


def test_a_failed_push_is_sent_again(client, loki, receiver):
    receiver.forward_once(now=NOW)
    client.put("/api/settings", json={"plugin.loki.tenant": "wrong"})
    receiver.receive(b"<14>one", "192.0.2.9", now=NOW + 1, check=False)
    receiver.forward_once(now=NOW + 1)
    assert receiver.status()["stores"][0]["error"] == "Loki refused the username or password."
    client.put("/api/settings", json={"plugin.loki.tenant": "hall"})
    receiver.forward_once(now=NOW + 2)
    last = [c for c in loki if c["url"].endswith("/push")][-1]
    assert json.loads(last["json"]["streams"][0]["values"][0][1])["message"] == "one"
    assert receiver.status()["stores"][0]["error"] is None


def test_search_with_logql(client, loki):
    body = client.get("/api/logs").get_json()
    assert "plugin:loki" in body["status"]["sources"]
    body = client.get('/api/logs?source=plugin:loki&q={device="sw-b-01"}&hours=6').get_json()
    assert [ln["message"] for ln in body["lines"]] == ["line 0", "line 1", "line 2"]
    first = body["lines"][0]
    assert first["seat"] == "B-3" and first["device"] == "sw-b-01" and first["id"] == int(NOW * 1e6)
    query = [c for c in loki if c["url"].endswith("/query_range")][-1]["params"]
    assert query["query"] == '{device="sw-b-01"}' and query["direction"] == "backward"
    assert int(query["end"]) - int(query["start"]) == 6 * 3600 * 10**9
    # Paging back: before is the oldest line's id, in microseconds.
    client.get(f"/api/logs?source=plugin:loki&before={int(NOW * 1e6)}")
    assert [c for c in loki if c["url"].endswith("/query_range")][-1]["params"]["end"] == str(int(NOW * 1e9))
    bad = client.get("/api/logs?source=plugin:loki&q={job=floorbit} |= err").get_json()
    assert bad["lines"] == [] and "parse error" in bad["status"]["query_error"]
    assert client.get("/api/logs?source=plugin:loki&hours=0").status_code == 400
    assert client.get("/api/logs?source=plugin:other").status_code == 404


def test_the_connection_test(client, loki):
    assert client.post("/api/settings/plugins/loki/test").get_json()["ok"] is True
