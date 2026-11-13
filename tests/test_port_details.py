"""Seat port view: reading one port from LibreNMS and summarising it. No real LibreNMS is called."""

import port_details

PORT = {
    'port_id': 812, 'device_id': 14, 'ifName': 'Gi1/0/14', 'ifAlias': 'seat A-14 ',
    'ifOperStatus': 'up', 'ifAdminStatus': 'up', 'ifDuplex': 'fullDuplex',
    'ifSpeed': 1_000_000_000, 'ifHighSpeed': 1000,
    'ifInOctets_rate': 2_500_000, 'ifOutOctets_rate': 10_000_000,
    'ifInErrors': 3, 'ifOutErrors': 0, 'ifInErrors_rate': 0, 'ifOutErrors_rate': 0,
    'poll_time': 1763060000,
}


def test_summary_uses_the_players_side():
    s = port_details.summarize_port(PORT, 'https://librenms.example.com/')
    assert s['download_bps'] == 80_000_000   # ifOut: switch to player
    assert s['upload_bps'] == 20_000_000     # ifIn: player to switch
    assert s['speed_bps'] == 1e9
    assert s['utilization'] == 0.08
    assert s['duplex'] == 'full'
    assert s['description'] == 'seat A-14'
    assert (s['errors_in'], s['errors_out'], s['error_rate']) == (3, 0, 0)
    assert s['state'] == 'up'
    assert s['librenms_url'] == 'https://librenms.example.com/device/device=14/tab=port/port=812/'
    # The seat heatmap still reads the raw counters.
    assert s['ifOperStatus'] == 'up' and s['ifInOctets_rate'] == 2_500_000


def test_state():
    summarize = port_details.summarize_port
    assert summarize({**PORT, 'ifInErrors_rate': 0.4})['state'] == 'errors'
    assert summarize({**PORT, 'ifOperStatus': 'down'})['state'] == 'down'
    assert summarize({**PORT, 'ifOperStatus': 'down'})['utilization'] is None
    assert summarize({**PORT, 'ifAdminStatus': 'down', 'ifOperStatus': 'down'})['state'] == 'disabled'
    assert summarize({'ifName': 'Gi1/0/1'})['state'] == 'unknown'


def test_high_speed_beats_capped_if_speed():
    s = port_details.summarize_port({**PORT, 'ifSpeed': 4_294_967_295, 'ifHighSpeed': 10_000})
    assert s['speed_bps'] == 10e9


def test_old_librenms_without_detail_columns():
    s = port_details.summarize_port({k: PORT[k] for k in port_details.BASE_COLUMNS})
    assert s['state'] == 'up'
    assert s['errors_in'] is None and s['error_rate'] is None and s['duplex'] is None
    assert s['librenms_url'] is None


class FakeResponse:
    def __init__(self, status, ports=()):
        self.status_code = status
        self.ok = status < 400
        self._ports = list(ports)

    def json(self):
        return {'ports': self._ports}


def test_fetch_port_falls_back_to_base_columns(monkeypatch):
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append(params['columns'])
        if 'ifAlias' in params['columns']:
            return FakeResponse(500)   # an older LibreNMS without one of the columns
        return FakeResponse(200, [{'ifName': 'Gi1/0/13'}, {'ifName': 'Gi1/0/14', 'port_id': 812}])

    monkeypatch.setattr(port_details.requests, 'get', fake_get)
    port = port_details.fetch_port('https://librenms.example.com', {}, 14, 'Gi1/0/14')
    assert port == {'ifName': 'Gi1/0/14', 'port_id': 812}
    assert len(calls) == 2


def test_fetch_port_unknown_name(monkeypatch):
    monkeypatch.setattr(port_details.requests, 'get', lambda *a, **k: FakeResponse(200, [{'ifName': 'Gi1/0/1'}]))
    assert port_details.fetch_port('https://librenms.example.com', {}, 14, 'Gi1/0/14') is None
