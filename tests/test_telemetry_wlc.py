"""A Catalyst 9800 wireless controller's MDT (docs/telemetry.md, "Wireless controllers"): its access
points, radios and their load in the telemetry picture and the Wi-Fi view, counts only."""
import time
import tomllib

import pytest

from floorbit import wifi
from floorbit.telemetry import state, storage, targets, telegraf

pytestmark = pytest.mark.usefixtures("lan_here")

WLC = {"name": "wlc-01", "address": "192.0.2.40", "mdt_node": "wlc-01", "drivers": ["mdt"], "platform": "iosxe",
       "wireless": True}
AP1, AP2 = "02:00:00:00:a0:01", "02:00:00:00:a0:02"


@pytest.fixture(autouse=True)
def fresh():
    state.state.reset()
    wifi.reset()
    state.state.know([WLC])
    yield
    state.state.reset()
    wifi.reset()


def stream(now, *lines):
    """Lines as Telegraf's cisco_telemetry_mdt input sends them, with the aliases from telegraf.py."""
    ns = str(int(now * 1e9))
    return state.state.apply_text("\n".join(f"{line} {ns}" for line in lines), now)


def hall(now):
    return stream(
        now,
        f'fb_wlc_ap,mdt_source=wlc-01,wtp_mac={AP1} name="ap-stage",device-detail/static-info/ap-models/model='
        '"C9136I-E",ap-state/ap-admin-state="adminstate-enabled",ap-state/ap-operation-state="registered"',
        f'fb_wlc_ap,mdt_source=wlc-01,wtp_mac={AP2} name="ap-hall-02",device-detail/static-info/ap-models/model='
        '"C9120AXI-E",ap-state/ap-operation-state="registered"',
        f'fb_wlc_radio,mdt_source=wlc-01,wtp_mac={AP1},radio_slot_id=0 oper-state="radio-up",'
        'admin-state="enabled",phy-ht-cfg/cfg-data/curr-freq=6i,phy-ht-cfg/cfg-data/chan-width="chan-width-20-mhz",'
        'current-active-band="dot11-2-dot-4-ghz-band"',
        f'fb_wlc_radio,mdt_source=wlc-01,wtp_mac={AP1},radio_slot_id=1 oper-state="radio-up",'
        'phy-ht-cfg/cfg-data/curr-freq=36i,phy-ht-cfg/cfg-data/chan-width="chan-width-80-mhz",'
        'current-active-band="dot11-5-ghz-band"',
        # An off radio is left out; a radio with only its slot still finds its band.
        f'fb_wlc_radio,mdt_source=wlc-01,wtp_mac={AP1},radio_slot_id=2 oper-state="radio-down",'
        'current-active-band="dot11-6-ghz-band"',
        f'fb_wlc_radio,mdt_source=wlc-01,wtp_mac={AP2},radio_slot_id=1 oper-state="radio-up",'
        'phy-ht-cfg/cfg-data/curr-freq=44i,phy-ht-cfg/cfg-data/chan-width="chan-width-40-mhz"',
        f'fb_wlc_rrm,mdt_source=wlc-01,wtp_mac={AP1},radio_slot_id=0 load/cca-util-percentage=31i,load/stations=4i',
        f'fb_wlc_rrm,mdt_source=wlc-01,wtp_mac={AP1},radio_slot_id=1 load/cca-util-percentage=78i,load/stations=41i',
        f'fb_wlc_rrm,mdt_source=wlc-01,wtp_mac={AP2},radio_slot_id=1 load/cca-util-percentage=12i,load/stations=7i')


def test_the_controllers_aps_in_the_picture():
    now = time.time()
    assert hall(now) == (9, 9, 0)     # understood, parsed, bad
    dev = state.state.device("wlc-01")
    assert dev.kind == "wlc"
    aps = {a["name"]: a for a in dev.wifi_aps(now)}
    assert aps["ap-stage"] == {"name": "ap-stage", "model": "C9136I-E", "status": "up", "radios": [
        {"band": "2.4", "channel": 6, "width": 20, "utilization": 31, "clients": 4},
        {"band": "5", "channel": 36, "width": 80, "utilization": 78, "clients": 41}]}
    assert aps["ap-hall-02"]["radios"] == [{"band": "5", "channel": 44, "width": 40, "utilization": 12, "clients": 7}]


def test_an_ap_that_left_reads_down_then_goes():
    now = time.time()
    hall(now)
    dev = state.state.device("wlc-01")
    later = now + state.STALE + 1
    assert {a["name"]: a["status"] for a in dev.wifi_aps(later)} == {"ap-stage": "down", "ap-hall-02": "down"}
    assert all(a["radios"] == [] for a in dev.wifi_aps(later))
    state.state._expire(now + state.AP_TTL + 1)
    assert dev.wifi_aps(now) == []


def test_a_spoofed_sender_adds_nothing():
    now = time.time()
    stream(now, f'fb_wlc_ap,mdt_source=rogue,wtp_mac={AP1} name="evil"')
    assert set(state.state.devices) == {"wlc-01"} and state.state.device("wlc-01").aps == {}


def test_the_wifi_view_takes_the_stream_first(app_module, client, monkeypatch):
    registry = app_module.app.extensions["floorbit_plugins"]
    assert client.put("/api/settings/plugins/telemetry", json={"enabled": True}).status_code == 200
    assert client.put("/api/settings/plugins/demo", json={"enabled": True}).status_code == 200
    hall(time.time())
    aps, errors = wifi.ask(registry)
    by = {a["name"]: a for a in aps}
    assert errors == [] and by["ap-stage"]["source"] == "Telemetry"
    assert by["ap-stage"]["clients"] == 45 and by["ap-stage"]["model"] == "C9136I-E"
    assert by["ap-02"]["source"] == "Demo data"       # the demo's other APs still come from it


def test_client_lists_are_never_stored(monkeypatch):
    from floorbit.telemetry import lineproto
    sent = []
    monkeypatch.setenv("FLOORBIT_VICTORIAMETRICS_URL", "http://vm.example.com:8428")
    monkeypatch.setattr(storage.Storage, "_vm_write", lambda self, url, lines: sent.extend(lines) or len(lines))
    points, _ = lineproto.parse(
        f'fb_wlc_rrm,mdt_source=wlc-01,wtp_mac={AP1},radio_slot_id=1 load/stations=41i\n'
        'Cisco-IOS-XE-wireless-client-oper:client-oper-data/common-oper-data,mdt_source=wlc-01,'
        'client_mac=02:00:00:00:c0:01 username="player-01"')
    storage.Storage(None).forward_raw(points)
    assert len(sent) == 1 and "player" not in sent[0] and sent[0].startswith("fb_wlc_rrm")


def test_telegraf_and_the_controllers_setup():
    conf = tomllib.loads(telegraf.render([WLC], "http://x/write", "tok"))
    aliases = conf["inputs"]["cisco_telemetry_mdt"][0]["aliases"]
    assert aliases["fb_wlc_ap"].endswith("access-point-oper-data/capwap-data")
    assert aliases["fb_wlc_rrm"] == "Cisco-IOS-XE-wireless-rrm-oper:rrm-oper-data/rrm-measurement"
    setup = telegraf.device_config(WLC, "192.0.2.10")
    assert "filter xpath /wireless-access-point-oper:access-point-oper-data/radio-oper-data" in setup
    assert "telemetry ietf subscription 104" in setup and "client" not in setup
    assert "subscription 102" not in telegraf.device_config({**WLC, "wireless": False}, "192.0.2.10")


@pytest.mark.parametrize("model, wireless", [("C9800-CL-K9", True), ("C9800-40-K9", True),
                                             ("C9300-48P", False), ("", False)])
def test_a_9800_is_known_by_its_model(model, wireless):
    t = targets._from_device({"id": "d1", "name": "wlc-01", "address": "192.0.2.40", "platform": "IOS-XE",
                              "model": model, "properties": {"telemetry_drivers": "mdt"}}, None, None)
    assert t["wireless"] is wireless and t["drivers"] == ["mdt"]
