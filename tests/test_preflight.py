"""Pre-flight check board (issue #35)."""
from floorbit import sources
from tests.test_attention import Monitoring, port
from tests.test_health import fake_checks, registry, service, wall  # noqa: F401  # fixtures
from tests.test_rbac import sign_in_as


class Devices(Monitoring):
    def __init__(self):
        super().__init__()
        self.status = {}

    def devices(self):
        return [{"display": name, "hostname": name, "status": up} for name, up in self.status.items()]


def test_the_board_checks_switches_uplinks_and_services(client, monkeypatch, wall, fake_checks):  # noqa: F811
    mon = Devices()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5})
    client.post("/api/switches", json={"name": "sw-b-01", "x": 60, "y": 5})
    client.post("/api/switches", json={"name": "sw-c-01", "x": 90, "y": 5})
    mon.status = {"sw-a-01": 1, "sw-b-01": 0}
    mon.set("sw-a-01", port("Te1/1/1", description="Uplink to dist-01"), port("Gi1/0/1", description="Seat A-1"))
    mon.set("sw-b-01", port("Te1/1/1", state="down", description="Uplink to dist-01"))
    fake_checks.extend([service("up", id="dhcp", name="DHCP", kind="dhcp"),
                        service("down", id="dns", name="DNS", kind="dns")])

    assert client.get("/api/preflight").get_json()["complete"] is False
    body = client.post("/api/preflight/run", json={}).get_json()
    sw = {i["name"]: i["status"] for i in body["groups"]["switches"]["items"]}
    assert sw == {"sw-a-01": "pass", "sw-b-01": "fail", "sw-c-01": "fail"}
    up = {i["name"]: i["status"] for i in body["groups"]["uplinks"]["items"]}
    assert up == {"sw-a-01 Te1/1/1": "pass", "sw-b-01 Te1/1/1": "fail", "sw-c-01": "warn"}
    svc = {i["name"]: i["status"] for i in body["groups"]["services"]["items"]}
    assert svc == {"DHCP": "pass", "DNS": "fail"}
    assert body["complete"] is True and body["ready"] is False
    assert wall.snapshot()["checks"] == []   # the wall's own state didn't move

    # Fix things and run one group again: the others keep their result.
    mon.status["sw-b-01"] = 1
    again = client.post("/api/preflight/run", json={"group": "switches"}).get_json()
    assert again["groups"]["uplinks"]["at"] == body["groups"]["uplinks"]["at"]
    assert again["counts"]["fail"] == 3
    assert client.post("/api/preflight/run", json={"group": "nope"}).status_code == 400
    pdf = client.get("/api/preflight.pdf?tz=-60")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_without_sources_checks_are_skipped(client):
    body = client.post("/api/preflight/run", json={}).get_json()
    assert body["groups"]["switches"]["items"][0]["status"] == "skip"
    assert body["groups"]["services"]["items"][0]["status"] == "warn"


def test_viewers_look_but_dont_run(app_module, client):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.get("/api/preflight").status_code == 200
    assert viewer.post("/api/preflight/run", json={}).status_code == 403
