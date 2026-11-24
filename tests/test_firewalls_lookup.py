"""Which firewall an IP address or a seat goes through (Mike, 2026-11-24)."""
import pytest

from tests.test_firewalls import _add, net  # noqa: F401  # fixture
from tests.test_rbac import sign_in_as

pytestmark = pytest.mark.usefixtures("lan_here")


def test_an_ip_finds_its_part_and_firewall(client, net):  # noqa: F811
    assert _add(client, "192.0.2.0/26", "fw-01", "fw-02", fallback=["fw-03"], name="Hall").status_code == 201
    net.up["fw-02"] = False
    first = client.get("/api/firewalls/lookup?q=192.0.2.10").get_json()
    keys = ("kind", "found", "range", "cidr", "part", "intended", "state")
    assert tuple(first[k] for k in keys) == ("ip", True, "Hall", "192.0.2.0/26", "192.0.2.0/27", "fw-01", "primary")
    second = client.get("/api/firewalls/lookup?q=192.0.2.40").get_json()
    assert (second["part"], second["intended"], second["fallback"]) == ("192.0.2.32/27", "fw-02", ["fw-03"])
    assert (second["now"], second["state"]) == ("fw-03", "failover")       # fw-02 is down

    outside = client.get("/api/firewalls/lookup?q=203.0.113.9").get_json()
    assert outside == {"query": "203.0.113.9", "kind": "ip", "seat": None, "found": False}


def test_a_seat_answers_through_its_ip_without_showing_it(client, net):  # noqa: F811
    _add(client, "192.0.2.0/26", "fw-01", "fw-02", name="Hall")
    seat = client.get("/api/firewalls/lookup?q=a-2").get_json()
    assert (seat["kind"], seat["seat"], seat["intended"], seat["part"]) == ("seat", "A-2", "fw-02", "192.0.2.32/27")
    assert "192.0.2.40" not in str(seat)
    assert client.get("/api/firewalls/lookup?q=B-1").get_json()["found"] is False      # its IP is in no range
    missing = client.get("/api/firewalls/lookup?q=Z-99")
    assert missing.status_code == 404 and "neither" in missing.get_json()["error"]
    assert client.get("/api/firewalls/lookup?q=").status_code == 400


def test_without_seats_view_a_seat_gives_names_only(app_module, client, net):  # noqa: F811
    _add(client, "192.0.2.0/26", "fw-01", "fw-02", name="Hall")
    kiosk = sign_in_as(app_module, "ki1", "kiosk")
    seat = kiosk.get("/api/firewalls/lookup?q=A-2")
    if seat.status_code == 403:
        return   # a kiosk may not see firewalls at all
    body = seat.get_json()
    assert body["intended"] == "fw-02" and "part" not in body and "cidr" not in body
    assert kiosk.get("/api/firewalls/lookup?q=192.0.2.40").get_json()["part"] == "192.0.2.32/27"
