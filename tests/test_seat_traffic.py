"""Seat level of the traffic heatmap: per-seat port throughput, looked up in parallel."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seat_traffic import collect_seat_heatmap, seat_port_usage  # noqa: E402

PORT = {'ifOperStatus': 'up', 'ifInOctets_rate': '1250000', 'ifOutOctets_rate': '250000',
        'ifSpeed': '1000000000'}


def fake_resolve(ip):
    return {'mac': 'aa:bb:cc:dd:ee:ff', 'device_name': 'sw-a1', 'port': 'ge-0/0/7',
            'vlan': '20', 'stats': PORT}


def test_throughput_is_in_plus_out_in_bits():
    entry = seat_port_usage({'username': 'neo', 'ip_address': '10.0.0.7'}, fake_resolve)
    assert entry['resolved'] is True
    usage = entry['port_usage']
    assert usage['in_rate_bps'] == 10_000_000
    assert usage['out_rate_bps'] == 2_000_000
    assert usage['total_bps'] == 12_000_000
    assert usage['status'] == 'up'
    assert usage['speed_bps'] == 1e9
    assert entry['device_name'] == 'sw-a1' and entry['port'] == 'ge-0/0/7'


def test_seat_without_ip_is_not_looked_up():
    def boom(ip):
        raise AssertionError('should not resolve')
    entry = seat_port_usage({'username': 'trin'}, boom)
    assert entry == {'username': 'trin', 'ip_address': None, 'resolved': False,
                     'port_usage': None, 'error': 'No IP address'}


def test_unresolved_and_failing_seats_do_not_break_the_map():
    def resolve(ip):
        if ip == '10.0.0.2':
            return None
        if ip == '10.0.0.3':
            raise RuntimeError('LibreNMS timed out')
        return fake_resolve(ip)

    seats = {f'A-{i}': {'ip_address': f'10.0.0.{i}'} for i in (1, 2, 3)}
    result = collect_seat_heatmap(seats, resolve)
    assert list(result) == ['A-1', 'A-2', 'A-3']
    assert result['A-1']['resolved'] is True
    assert result['A-2']['error'] == 'Could not resolve port stats'
    assert result['A-3']['resolved'] is False
    assert 'LibreNMS timed out' in result['A-3']['error']


def test_lookups_run_in_parallel():
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow_resolve(ip):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return fake_resolve(ip)

    seats = {f'B-{i}': {'ip_address': f'10.0.1.{i}'} for i in range(16)}
    started = time.monotonic()
    result = collect_seat_heatmap(seats, slow_resolve, max_workers=8)
    elapsed = time.monotonic() - started
    assert len(result) == 16 and all(e['resolved'] for e in result.values())
    assert peak > 1
    assert elapsed < 16 * 0.05 / 2


def test_empty_mapping():
    assert collect_seat_heatmap({}, fake_resolve) == {}
