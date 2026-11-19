"""floorbit.plugins.helpers: what Marketplace plugins may import from Floorbit (docs/plugin-spec.md)."""

import pytest

from floorbit.plugins import helpers
from floorbit.plugins.base import PluginError


def test_port_summary_and_device_match():
    port = {"ifName": "Gi1/0/1", "ifOperStatus": "up", "ifAdminStatus": "up", "ifInOctets_rate": 1000,
            "ifOutOctets_rate": 0, "ifSpeed": 1_000_000_000}
    assert helpers.summarize_port(port)["state"] == "up"
    devices = [{"display": "sw-a-01.hall.example", "hostname": "192.0.2.10"}, {"display": "sw-b-01"}]
    assert helpers.match_device("sw-a-01", devices) is devices[0]
    assert helpers.match_device("sw-c-01", devices) is None


def test_mac_and_uplinks(monkeypatch):
    assert helpers.normalise_mac("02-00-00-00-00-AA") == "02:00:00:00:00:aa"
    assert helpers.normalise_mac("nope") is None
    assert helpers.uplink_pattern().search("Uplink to core")
    from integrations import config
    monkeypatch.setattr(config, "get", lambda key, default=None: "(" if key == "STATS_UPLINK_PATTERN" else default)
    assert helpers.uplink_pattern().pattern == helpers.DEFAULT_UPLINK      # a broken pattern falls back


def test_parse_switches():
    assert helpers.parse_switches(["sw-a = https://192.0.2.10:8443/x"]) == [{"name": "sw-a", "url": "https://192.0.2.10:8443"}]
    for bad in ("sw-a", "=https://192.0.2.10", "sw-a=ftp://192.0.2.10"):
        with pytest.raises(PluginError, match="not Name="):
            helpers.parse_switches([bad])
