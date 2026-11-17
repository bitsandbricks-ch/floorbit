"""Seat level of the traffic heatmap: per-seat port throughput, looked up in parallel."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from floorbit.seat_traffic import collect_seat_heatmap, resolve_seats, seat_port_usage

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
                     'port_usage': None, 'error': 'No switch port or IP address'}


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


def test_resolve_seats_skips_seats_without_an_ip_and_survives_a_bad_lookup():
    def resolve(ip):
        if ip == '192.0.2.3':
            raise RuntimeError('LibreNMS timed out')
        return None if ip == '192.0.2.2' else {'device_name': 'sw-a1', 'port': 'ge-0/0/7'}
    seats = {'A-1': {'username': 'neo', 'ip_address': '192.0.2.1'}, 'A-2': {'ip_address': '192.0.2.2'},
             'A-3': {'ip_address': '192.0.2.3'}, 'A-4': {'username': 'trin'}, 'A-5': None}
    got = resolve_seats(seats, resolve)
    assert set(got) == {'A-1', 'A-2', 'A-3'}
    assert got['A-1'] == {'username': 'neo', 'ip_address': '192.0.2.1', 'resolved': True,
                          'device_name': 'sw-a1', 'port': 'ge-0/0/7'}
    assert got['A-2'] == {'username': None, 'ip_address': '192.0.2.2', 'resolved': False, 'error': 'Could not resolve'}
    assert got['A-3']['resolved'] is False and 'timed out' in got['A-3']['error']


def test_resolve_seats_runs_in_parallel():
    seen, lock = [], threading.Lock()
    def slow(ip):
        with lock:
            seen.append(threading.get_ident())
        time.sleep(0.05)
        return {'port': 'x'}
    seats = {f'A-{i}': {'ip_address': f'192.0.2.{i}'} for i in range(1, 17)}
    start = time.monotonic()
    assert len(resolve_seats(seats, slow)) == 16
    assert time.monotonic() - start < 0.5 and len(set(seen)) > 1


def test_a_mapped_port_is_read_without_an_ip():
    def boom(ip):
        raise AssertionError('should not resolve')
    asked = []

    def port_stats(switch, port):
        asked.append((switch, port))
        return {'ifInOctets_rate': 1000, 'ifOutOctets_rate': 3000, 'ifOperStatus': 'up', 'ifSpeed': 1e9}
    entry = seat_port_usage({'username': 'trin', 'switch': 'sw-a1', 'port': 'Gi1/0/7'}, boom, port_stats)
    assert asked == [('sw-a1', 'Gi1/0/7')]
    assert entry['resolved'] and entry['ip_address'] is None
    assert (entry['device_name'], entry['port']) == ('sw-a1', 'Gi1/0/7')
    assert entry['port_usage']['total_bps'] == 32_000


def test_a_port_monitoring_does_not_know_falls_back_to_the_ip():
    seat = {'switch': 'sw-a1', 'port': 'Gi1/0/99', 'ip_address': '10.0.0.1'}
    entry = seat_port_usage(seat, fake_resolve, lambda switch, port: {})
    assert entry['resolved'] and entry['port'] == 'ge-0/0/7'


def test_the_heatmap_reads_mapped_ports():
    seats = {'A-1': {'switch': 'sw-a1', 'port': 'Gi1/0/1'}, 'A-2': {}}
    got = collect_seat_heatmap(seats, fake_resolve, port_stats=lambda s, p: {'ifOperStatus': 'up'})
    assert got['A-1']['resolved'] and got['A-1']['port_usage']['status'] == 'up'
    assert got['A-2']['error'] == 'No switch port or IP address'
