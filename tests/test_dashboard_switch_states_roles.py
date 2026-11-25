"""The "Switch states" tile lists switches, not access points or servers (#1407)."""
from floorbit import dashboard_core


def test_switch_states_leave_out_devices_that_are_not_switches():
    statuses = {
        "sw": {"id": "sw", "name": "sw-a-01", "status": "online", "since": 0},
        "core": {"id": "core", "name": "core-01", "status": "offline", "since": 0},
        "ap": {"id": "ap", "name": "ap-01", "status": "online", "since": 0},
        "srv": {"id": "srv", "name": "cache-01", "status": "online", "since": 0},
        "new": {"id": "new", "name": "sw-new", "status": "online", "since": 0},
    }
    roles = {"sw": "switch", "core": "router", "ap": "access_point", "srv": "server"}
    body = dashboard_core.switch_states_widget("en", statuses, now=60, roles=roles)
    assert [i["label"] for i in body["items"]] == ["core-01", "sw-a-01", "sw-new"]
    # Without roles (a plugin asking the old way) every device stays.
    assert len(dashboard_core.switch_states_widget("en", statuses, now=60)["items"]) == 5
