"""The server's clock set back (NTP correcting a box that booted an hour ahead, a VM restored from a
snapshot): a window that started "in the future" must end, not last until the clock catches up."""
import time

from integrations import checkin
from integrations.discord import DiscordNotifier

HOUR = 3600


def offline(sid="sw-1", name="sw-a-01"):
    return {"id": sid, "name": name, "status": "offline", "previous": "online"}


def test_a_down_alert_after_the_clock_went_back_still_pages(client):
    notifier = DiscordNotifier()
    now = time.time()
    assert notifier.build_status_message([offline()], now=now) is not None
    assert notifier.build_status_message([offline()], now=now + 60) is None     # the cooldown, as before
    # Before: an hour back, the switch could go down and up again for an hour with nobody told.
    assert notifier.build_status_message([offline()], now=now - HOUR) is not None


def test_service_security_and_power_alerts_too(client):
    notifier, now = DiscordNotifier(), time.time()
    down = {"id": "dns", "name": "DNS", "status": "down", "previous": "up"}
    assert notifier.build_health_message([down], now=now) is not None
    assert notifier.build_health_message([down], now=now - HOUR) is not None
    finding = {"id": "f1", "severity": "high", "kind": "rogue_dhcp", "switch": "sw-a-01", "port": "Gi1/0/1"}
    assert notifier.build_security_message(finding, now=now) is not None
    assert notifier.build_security_message(finding, now=now - HOUR) is not None
    alert = {"id": "c1", "state": "tripped", "name": "Row A"}
    assert notifier.build_power_message(alert, now=now) is not None
    assert notifier.build_power_message(alert, now=now - HOUR) is not None


def test_a_login_lockout_ends_when_the_clock_goes_back(anon_client, app_module, monkeypatch):
    import auth as auth_pkg
    guard = app_module.app.extensions["auth"]
    real = time.time()
    with app_module.app.test_request_context("/login", method="POST"):
        for _ in range(auth_pkg.MAX_FAILURES):
            guard.record_failure("admin")
        assert 0 < guard.locked_for("admin") <= auth_pkg.FAILURE_WINDOW + 1
        monkeypatch.setattr(auth_pkg.time, "time", lambda: real - HOUR)
        # Before: "try again in 65 minutes", for an account the crew needs now.
        assert guard.locked_for("admin") == 0


def test_wrong_pins_from_before_the_clock_went_back_do_not_hold_the_pc(monkeypatch):
    monkeypatch.setattr(checkin, "_wrong_pins", {})
    now = time.time()
    for _ in range(20):
        checkin._wrong_pin("192.0.2.10", now)
    assert checkin._wrong_pin_wait("192.0.2.10", now) > 0
    assert checkin._wrong_pin_wait("192.0.2.10", now - HOUR) == 0
