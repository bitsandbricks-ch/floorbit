"""The seat walk's live trace (issue #1359): every step of a Locate, in order, for the page.
Demo hall, RFC 5737 addresses and example MACs only."""
from floorbit import checkin_lookup, seat_walk
from floorbit.telemetry import lookup, snmpget
from integrations import events
from tests.test_seat_walk import Monitor, demo_seat, hall, locate  # noqa: F401  # hall is a fixture

MAC = '02:00:00:00:00:31'


def codes(steps):
    return [(s['code'], s['state']) for s in steps]


def test_the_agent_says_how_long_each_switch_took_and_what_it_said():
    def get(target, oids, vlan=None, timeout=None):
        if target['name'] == 'dead':
            raise snmpget.SnmpError('dead: timeout')
        if target['name'] == 'empty':
            return {oids[0]: None}
        return {oids[0]: 3 if oids[0].startswith(snmpget.FDB_PORT) else 10103}
    targets = [{'name': n, 'address': '192.0.2.9'} for n in ('dead', 'empty', 'live')]
    out = lookup.find({'ip': '192.0.2.23', 'vlan': 110, 'mac': MAC, 'switches': ['dead', 'empty', 'live']},
                      targets, None, get=get)
    assert [(t['switch'], t['result']) for t in out['trail']] == [
        ('dead', 'error'), ('empty', 'none'), ('live', 'found')]
    assert all(isinstance(t['ms'], int) for t in out['trail']) and out['trail'][-1]['if_index'] == 10103


def test_each_switch_asked_is_named_with_its_group():
    trace = seat_walk.Trace()
    got = {'mac': MAC, 'switch': 'access-a1', 'port': 'Gi1/0/7',
           'trail': [{'switch': 'access-a1', 'ms': 30, 'result': 'none'},
                     {'switch': 'access-b1', 'ms': 40, 'result': 'uplink', 'if_index': 49},
                     {'switch': 'access-c1', 'ms': 50, 'result': 'found', 'port': 'Gi1/0/7'}]}
    checkin_lookup._trail(trace, got, {'row': ['access-a1'], 'block': ['access-b1'], 'vlan': ['access-c1']}, MAC)
    assert [(s['args']['switch'], s['args']['group'], s['state'], s.get('ms')) for s in trace.steps] == [
        ('access-a1', 'row', 'no', 30), ('access-b1', 'block', 'skip', 40), ('access-c1', 'vlan', 'ok', 50)]


def test_an_older_agent_without_a_trail_still_gets_one():
    trace = seat_walk.Trace()
    got = {'mac': MAC, 'switch': 'live', 'port': 'Gi1/0/3', 'asked': ['dead', 'up', 'live'],
           'skipped': [{'switch': 'up', 'if_index': 49}], 'errors': [{'switch': 'dead', 'error': 'timeout'}]}
    checkin_lookup._trail(trace, got, {'row': ['dead', 'up', 'live'], 'block': [], 'vlan': []}, None)
    assert codes(trace.steps) == [('snmpMac', 'ok'), ('snmpSwitch', 'no'), ('snmpSwitch', 'skip'), ('snmpSwitch', 'ok')]
    assert trace.steps[1]['args']['error'] == 'timeout' and trace.steps[3]['args']['port'] == 'Gi1/0/3'


def test_a_locate_answers_with_its_trace_and_sends_each_step_live(hall, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(events, 'publish', lambda kind, data=None, origin=None: sent.append((kind, data)))
    ip, _mac, _switch, port = demo_seat('A-1')
    r = locate(hall, 'A-1', ip, run='run-0123456789').get_json()
    assert r['ok'] and r['agent'] == 'Hall agent'
    steps = r['trace']
    assert steps[0]['code'] == 'hello' and steps[0]['args'] == {'agent': 'Hall agent', 'ip': ip}
    assert steps[-1]['code'] == 'found' and steps[-1]['args']['port'] == port
    live = [d for k, d in sent if k == 'seat-walk.trace']
    assert [d['step'] for d in live] == steps and {d['run'] for d in live} == {'run-0123456789'}
    assert all(d['seat'] == 'A-1' for d in live)


def test_no_live_steps_without_a_proper_run_id(hall, monkeypatch):  # noqa: F811
    sent = []
    monkeypatch.setattr(events, 'publish', lambda kind, data=None, origin=None: sent.append(kind))
    r = locate(hall, 'A-1', demo_seat('A-1')[0], run='bad id!').get_json()
    assert r['trace'] and 'seat-walk.trace' not in sent


def test_the_live_bus_never_shows_the_laptop_to_a_page_that_may_not_read_it():
    step = {'code': 'hello', 'state': 'ok', 'args': {'agent': 'Hall agent', 'ip': '192.0.2.23', 'mac': MAC}}
    assert events.scrub({'run': 'x', 'step': step})['step']['args'] == {'agent': 'Hall agent'}


def test_a_stale_answer_and_the_wait_show_in_the_trace(app_module, monkeypatch):
    from floorbit import sources
    monitor = Monitor([('sw-a-01', 'Gi1/0/1'), ('sw-a-01', 'Gi1/0/2')])
    monkeypatch.setattr(sources, 'monitoring', lambda: monitor)
    ticks = iter(range(0, 1000, 3))
    with app_module.app.app_context():
        r = seat_walk.locate('192.0.2.50', None, previous={'switch': 'sw-a-01', 'port': 'Gi1/0/1'},
                             sleep=lambda s: None, clock=lambda: next(ticks))
    got = [c for c, _s in codes(r['trace'])]
    assert got.index('stale') < got.index('wait') < got.index('found')
    assert r['trace'][-1]['args'] == {'how': 'monitoring', 'switch': 'sw-a-01', 'port': 'Gi1/0/2'}
