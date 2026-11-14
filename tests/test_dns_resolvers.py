"""AdGuard Home and Pi-hole as DNS sources (issue #87). Fake APIs, never a real resolver."""
import pytest
import requests

T0 = 1_794_650_400


class Answer:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not JSON")
        return self._body


def iso(ts):
    from datetime import UTC, datetime
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")


# Newest first, like AdGuard Home's log: 1200 lookups one second apart.
ADGUARD = [{"time": iso(T0 + 1200 - i), "question": {"name": f"cdn{i % 3}.steamcontent.com", "type": "A"},
            "client": f"198.51.100.{i % 50 + 1}",
            "reason": "FilteredBlackList" if i % 10 == 0 else "NotFilteredNotFound"}
           for i in range(1200)]


@pytest.fixture
def registry(app_module):
    app_module.app.extensions["floorbit_dns"].stop()
    return app_module.app.extensions["floorbit_plugins"]


@pytest.fixture
def adguard(client, registry, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        assert url == "https://dns.example.com/control/querylog" and method == "GET"
        calls.append(dict(kw["params"]))
        if self.auth != ("floorbit", "example-password"):
            return Answer({}, 401)
        start = 0
        if "older_than" in kw["params"]:
            start = next(i for i, r in enumerate(ADGUARD) if r["time"] == kw["params"]["older_than"]) + 1
        page = ADGUARD[start:start + kw["params"]["limit"]]
        return Answer({"data": page, "oldest": page[-1]["time"] if page else ""})

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={"plugin.adguard-home.url": "https://dns.example.com",
                                      "plugin.adguard-home.username": "floorbit",
                                      "plugin.adguard-home.password": "example-password"})
    assert client.put("/api/settings/plugins/adguard-home", json={"enabled": True}).status_code == 200
    return calls


def test_adguard_reads_back_to_the_cursor(registry, adguard):
    spec = registry.specs["adguard-home"]
    got = registry.call(spec, "dns_queries", T0 + 1200 - 700)
    assert len(got) == 701 and len(adguard) == 2                  # two pages of 500
    assert adguard[1]["older_than"] == ADGUARD[499]["time"]
    assert got[0] == {"ts": T0 + 1200 + 0.123456, "domain": "cdn0.steamcontent.com", "client": "198.51.100.1",
                      "blocked": True}
    assert sum(e["blocked"] for e in got) == 71
    assert min(e["ts"] for e in got) > T0 + 500


def test_adguard_explains_a_wrong_password(client, adguard):
    client.put("/api/settings", json={"plugin.adguard-home.password": "wrong"})
    body = client.post("/api/settings/plugins/adguard-home/test").get_json()
    assert body["ok"] is False and body["message"] == "AdGuard Home refused the username or password."
    client.put("/api/settings", json={"plugin.adguard-home.password": "example-password"})
    assert client.post("/api/settings/plugins/adguard-home/test").get_json()["ok"] is True


PIHOLE = [{"id": i, "time": T0 + 1500 - i + 0.5, "type": "A", "domain": "gateway.discord.gg",
           "client": {"ip": f"198.51.100.{i % 40 + 1}", "name": None},
           "status": "GRAVITY" if i % 4 == 0 else "FORWARDED"}
          for i in range(1500)]


@pytest.fixture
def pihole(client, registry, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        path = url.removeprefix("https://pihole.example.com")
        calls.append((method, path, kw.get("params"), self.headers.get("X-FTL-SID")))
        if method == "POST" and path == "/api/auth":
            ok = kw["json"]["password"] == "example-app-password"
            return Answer({"session": {"valid": ok, "sid": "example-sid" if ok else None}}, 200 if ok else 401)
        if self.headers.get("X-FTL-SID") != "example-sid":
            return Answer({"error": {"key": "unauthorized"}}, 401)
        if method == "DELETE":
            return Answer({}, 204)
        p = kw["params"]
        if p.get("from") is None:
            return Answer({"queries": PIHOLE[:1], "recordsTotal": len(PIHOLE)})
        rows = [r for r in PIHOLE if p["from"] <= r["time"] < p["until"]]
        return Answer({"queries": rows[p["start"]:p["start"] + p["length"]], "recordsTotal": len(PIHOLE)})

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={"plugin.pihole.url": "https://pihole.example.com",
                                      "plugin.pihole.password": "example-app-password"})
    assert client.put("/api/settings/plugins/pihole", json={"enabled": True}).status_code == 200
    return calls


def test_pihole_signs_in_reads_pages_and_signs_out(registry, pihole, monkeypatch):
    import time
    monkeypatch.setattr(time, "time", lambda: T0 + 2000)
    spec = registry.specs["pihole"]
    got = registry.call(spec, "dns_queries", T0 + 100)
    assert len(got) == 1401 and all(e["ts"] > T0 + 100 for e in got)
    assert got[0] == {"ts": T0 + 1500.5, "domain": "gateway.discord.gg", "client": "198.51.100.1", "blocked": True}
    methods = [(m, p) for m, p, _params, _sid in pihole]
    assert methods == [("POST", "/api/auth"), ("GET", "/api/queries"), ("GET", "/api/queries"), ("DELETE", "/api/auth")]
    assert pihole[2][2]["start"] == 1000


def test_pihole_explains_a_wrong_password(client, pihole):
    client.put("/api/settings", json={"plugin.pihole.password": "wrong"})
    body = client.post("/api/settings/plugins/pihole/test").get_json()
    assert body["ok"] is False and body["message"] == "Pi-hole refused the password."
    client.put("/api/settings", json={"plugin.pihole.password": "example-app-password"})
    body = client.post("/api/settings/plugins/pihole/test").get_json()
    assert body == {**body, "ok": True} and "1500 lookups kept" in body["message"]


def test_both_feed_the_dns_area(registry):
    assert {"adguard-home", "pihole"} <= {s.id for s in registry.specs.values() if "dns" in s.manifest.get("uses", [])}
