"""The local agent program (issue #2) against the hosted side, all in one process.

The agent's HTTP goes through the Flask test client, so nothing leaves the process."""
import os
import threading
import time

import pytest

from floorbit import agent as agent_mod
from floorbit import agent_link, sources
from tests.test_agent import clean_tunnel, enrol  # noqa: F401  # the fixture resets the tunnel


class _Resp:
    def __init__(self, r):
        self.status_code = r.status_code
        self._r = r

    def json(self):
        return self._r.get_json()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


class ClientHttp:
    """What the agent needs from requests.Session, backed by the Flask test client."""

    def __init__(self, client):
        self.client = client

    def get(self, url, params=None, headers=None, timeout=None):
        return _Resp(self.client.get(url.replace('http://hosted.example.com', ''), query_string=params,
                                     headers=headers))

    def post(self, url, data=None, headers=None, timeout=None):
        return _Resp(self.client.post(url.replace('http://hosted.example.com', ''), data=data, headers=headers))


def fake_execute(method, args):
    if method == 'devices':
        return [{'hostname': 'sw-a-01', 'status': 1}]
    if method == 'device_details':
        return {'status': 'online', 'hostname': args[0]}
    raise RuntimeError('LibreNMS said no')


def make(app_module, key, execute=fake_execute):
    return agent_mod.Agent('http://hosted.example.com/', key, execute,
                           http=ClientHttp(app_module.app.test_client()), version='9.9.9', log=lambda *_: None)


def test_the_agent_answers_the_hosted_monitoring(client, app_module):
    key = enrol(client)['key']
    a = make(app_module, key)
    a.poll_wait = 0.5          # so stop() is quick
    assert a.hello()['name'] == 'Demo LAN 2026'
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        assert sources.monitoring().devices() == [{'hostname': 'sw-a-01', 'status': 1}]
        assert sources.monitoring().device_details('sw-a-01')['status'] == 'online'
        assert sources.monitoring().resolve_ip('192.0.2.10') is None     # the plugin's error: no answer
        listed = client.get('/api/agents').get_json()['agents'][0]
        assert listed['connected'] and listed['version'] == '9.9.9'
        stats = listed['stats']    # the page's "calls in the last hour"
        assert stats['calls'] >= 3 and stats['failed'] >= 1 and stats['median_ms'] is not None
        assert stats['last_error']['method'] == 'resolve_ip' and 'said no' in stats['last_error']['error']
    finally:
        a.stop()
        worker.join(30)
    assert not worker.is_alive()
    assert a.answered >= 3


def test_odd_answers_still_go_back(client, app_module):
    """A plugin answer JSON doesn't know (a date, say) is sent as text, not dropped."""
    import datetime
    key = enrol(client)['key']
    a = make(app_module, key, lambda m, args: {'when': datetime.date(2026, 11, 15)})
    agent_link.tunnel.seen()
    got = {}

    def ask():
        got['answer'] = agent_link.tunnel.call('devices', timeout=5)

    asker = threading.Thread(target=ask)
    asker.start()
    deadline = time.time() + 5
    while not got and time.time() < deadline:
        a.poll(wait=0.2)
        time.sleep(0.05)
    asker.join(5)
    assert got['answer'] == {'when': '2026-11-15'}


def test_a_revoked_key_stops_the_agent(client, app_module):
    made = enrol(client)
    client.delete(f"/api/agents/{made['id']}")
    with pytest.raises(agent_mod.Refused):
        make(app_module, made['key']).run()


def test_an_unreachable_host_is_retried(app_module):
    tries = []

    class Down:
        def get(self, *a, **k):
            tries.append(1)
            if len(tries) >= 2:
                agent.stop()
            raise ConnectionError('no route to host')

    agent = agent_mod.Agent('https://hosted.example.com', 'fba_x', fake_execute, http=Down(), log=lambda *_: None)
    started = time.time()
    agent.run()
    assert len(tries) == 2 and time.time() - started < 5     # waited 1 s between tries, then stopped


def test_main_wants_its_settings(monkeypatch, capsys):
    monkeypatch.delenv('FLOORBIT_URL', raising=False)
    monkeypatch.delenv('FLOORBIT_AGENT_KEY', raising=False)
    assert agent_mod.main([]) == 2
    monkeypatch.setenv('FLOORBIT_URL', 'http://hosted.example.com')
    monkeypatch.setenv('FLOORBIT_AGENT_KEY', 'fba_00000000_' + 'x' * 30)
    monkeypatch.delenv('FLOORBIT_AGENT_INSECURE', raising=False)
    assert agent_mod.main([]) == 2
    assert 'https://' in capsys.readouterr().err


def test_the_local_executor_only_runs_monitoring_methods(app_module):
    from floorbit.plugins.base import PluginError
    execute = agent_mod.local_executor(app_module.app)
    with pytest.raises(PluginError):
        execute('delete_everything', [])


def test_the_inventory_comes_through_the_agent(client, app_module):
    """A hosted sync asks the agent for its NetBox devices, kept under NetBox's own id."""
    key = enrol(client)['key']

    def execute(method, args):
        if method == 'inventory_feeds':
            return [{'plugin': 'netbox', 'name': 'NetBox', 'items': [
                        {'id': '7', 'name': 'sw-a-01', 'role': 'switch', 'model': 'X1'}]},
                    {'plugin': 'other', 'name': 'Other', 'error': 'Other said no'},
                    {'plugin': 'Not An Id!', 'name': 'x', 'items': []}]
        return fake_execute(method, args)

    a = make(app_module, key, execute)
    a.poll_wait = 0.5
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        res = client.post('/api/inventory/sync', headers={'X-Requested-With': 'fetch'})
        assert res.status_code == 200, res.get_json()
        reports = {r['plugin']: r for r in res.get_json()['reports'] if r.get('via') == 'agent'}
        assert reports['netbox']['added'] == 1, reports['netbox']
        assert 'error' in reports['other'] and 'Not An Id!' not in reports
        devices = client.get('/api/inventory').get_json()
        assert [d['name'] for d in devices['devices']] == ['sw-a-01']
        by_id = {s['id']: s for s in devices['sources']}
        # NetBox is on here too, but the agent fed it, so it isn't asked here (it would only fail).
        assert by_id['netbox']['last_sync']['via'] == 'agent'
        assert by_id['netbox']['name'] == 'NetBox (local agent)'
        assert not [r for r in res.get_json()['reports'] if r['plugin'] == 'netbox' and r.get('via') != 'agent']
        assert by_id['other']['name'] == 'Other (local agent)' and 'agent' not in by_id
    finally:
        a.stop()
        worker.join(30)


def test_an_away_agent_is_a_failed_sync(client):
    enrol(client)
    res = client.post('/api/inventory/sync', headers={'X-Requested-With': 'fetch'})
    agent = [r for r in res.get_json()['reports'] if r.get('via') == 'agent']
    assert agent and 'not connected' in agent[0]['error']
    names = [s['name'] for s in client.get('/api/inventory').get_json()['sources']]
    assert 'Local agent' in names


def test_the_agent_sends_its_inventory_plugins(app_module):
    from floorbit.plugins.base import PluginError

    class Spec:
        def __init__(self, i):
            self.id, self.name = i, i.title()

    class Registry:
        def feeders(self, area):
            return [Spec('netbox'), Spec('broken')] if area == 'inventory' else []

        def call(self, spec, method):
            if spec.id == 'broken':
                raise PluginError('down')
            return [{'id': '1', 'name': 'sw-01'}]

    assert agent_mod.inventory_feeds(Registry()) == [
        {'plugin': 'netbox', 'name': 'Netbox', 'items': [{'id': '1', 'name': 'sw-01'}]},
        {'plugin': 'broken', 'name': 'Broken', 'error': 'down'}]


def test_cables_come_through_the_agent(client, app_module):
    """A hosted cable import takes the agent's NetBox cables and doesn't ask the hosted NetBox."""
    key = enrol(client)['key']

    def execute(method, args):
        if method == 'cable_feeds':
            return [{'plugin': 'netbox', 'name': 'NetBox', 'items': [
                {'switch': 'sw-a-01', 'port': 'Gi1/0/5', 'seat': 'A-5', 'label': 'K-5'}]}]
        return fake_execute(method, args)

    a = make(app_module, key, execute)
    a.poll_wait = 0.5
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        assert 'Local agent' in client.get('/api/cables').get_json()['sources']
        res = client.post('/api/cables/import')
        assert res.status_code == 200, res.get_json()
        assert res.get_json() == {'imported': 1, 'errors': []}    # no "set up NetBox" from this side
        cable = client.get('/api/cables').get_json()['cables'][0]
        assert (cable['switch'], cable['port'], cable['plugin']) == ('sw-a-01', 'Gi1/0/5', 'NetBox')
    finally:
        a.stop()
        worker.join(30)


def test_cables_with_the_agent_away(client):
    enrol(client)
    res = client.post('/api/cables/import')
    assert res.status_code == 502 and 'Local agent' in res.get_json()['error']


def test_the_agent_sends_its_cable_plugins(app_module):
    with app_module.app.app_context():
        from floorbit import sources as srcs
        feeds = agent_mod.cable_feeds(srcs.registry)
    # NetBox is on by default but not set up here: its error comes back, not an exception.
    assert [f['plugin'] for f in feeds] == ['netbox'] and 'error' in feeds[0]


def test_an_away_agent_is_one_alert_that_says_so(client, app_module, monkeypatch):
    """The status monitor's outage message names the agent, not LibreNMS, and when it was last heard."""
    from floorbit import timeline, webhooks
    from integrations import events
    from integrations.discord import DiscordNotifier
    from integrations.monitor import StatusMonitor
    monkeypatch.setattr(events, '_subscribers', [])
    got = []
    events.subscribe('*', lambda ev: got.append(ev))
    key = enrol(client)['key']
    monitor = StatusMonitor(lambda: [{'id': '1', 'name': 'sw-a-01'}])
    agent_link.tunnel.last_seen = time.time() - 120      # it was here two minutes ago, then went away
    from floorbit.plugins.base import PluginError
    for _ in range(2):
        with pytest.raises(PluginError):
            monitor.poll_once()
    away = [e for e in got if e['type'] == 'monitoring.offline']
    assert len(away) == 1 and away[0]['data']['agent'] is True and away[0]['data']['last_seen']

    embed = DiscordNotifier().build_source_message('monitoring.offline', away[0]['data'])['embeds'][0]
    assert embed['title'] == '⚠️ The local agent is away' and '<t:' in embed['description']
    assert 'LibreNMS' not in embed['description']
    assert timeline.describe(away[0])[0] == 'Local agent away'
    assert webhooks.translate(away[0])[0][1]['agent'] is True

    # Back: the agent answers the next poll.
    a = make(app_module, key)
    a.poll_wait = 0.5
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        monitor.poll_once()
    finally:
        a.stop()
        worker.join(30)
    back = [e for e in got if e['type'] == 'monitoring.online']
    assert len(back) == 1 and back[0]['data']['agent'] is True
    embed = DiscordNotifier().build_source_message('monitoring.online', back[0]['data'])['embeds'][0]
    assert embed['title'] == '✅ The local agent is back'


def test_stats_forget_the_last_hour():
    agent_link.tunnel.seen()
    done = threading.Event()

    def ask():
        with pytest.raises(agent_link.AgentError):
            agent_link.tunnel.call('arp', ('sw-a-01',), timeout=5)
        done.set()

    threading.Thread(target=ask).start()
    deadline = time.time() + 5
    got = []
    while not got and time.time() < deadline:
        got = agent_link.tunnel.take(wait=0.2, agent='abcd1234')
    agent_link.tunnel.answer(got[0]['id'], False, error='no ARP here')
    done.wait(5)
    assert agent_link.tunnel.stats('abcd1234')['failed'] == 1
    assert agent_link.tunnel.stats('abcd1234', now=time.time() + 3601)['calls'] == 0
    assert agent_link.tunnel.stats('someone-else')['calls'] == 0


def test_check_says_what_works(client, app_module):
    key = enrol(client)['key']
    lines = []

    def execute(method, args):
        if method == 'inventory_feeds':
            return [{'plugin': 'netbox', 'name': 'NetBox', 'items': [{'id': '1', 'name': 'sw-01'}]}]
        if method == 'health_feeds':
            return [{'plugin': 'http-check', 'name': 'HTTP check', 'items': [{'id': 'cache'}]}]
        return fake_execute(method, args)

    assert agent_mod.check(make(app_module, key), execute, lines.append) is True
    assert lines[0].startswith('OK') and 'Demo LAN 2026' in lines[0]
    assert 'OK   the monitoring plugin answers: 1 devices' in lines
    assert 'OK   NetBox answers: 1 devices' in lines and lines[-1].startswith('All good')
    assert 'OK   HTTP check answers: 1 health checks' in lines


def test_check_names_what_fails(client, app_module, monkeypatch):
    monkeypatch.setenv('LIBRENMS_URL', 'https://librenms.example.com')
    made = enrol(client)
    client.delete(f"/api/agents/{made['id']}")
    lines = []

    def execute(method, args):
        if method in ('inventory_feeds', 'health_feeds'):
            return []
        raise RuntimeError('LibreNMS answered 401')

    assert agent_mod.check(make(app_module, made['key']), execute, lines.append) is False
    assert 'FAIL the monitoring plugin: LibreNMS answered 401' in lines
    monkeypatch.delenv('LIBRENMS_URL')
    lines.clear()

    assert agent_mod.check(make(app_module, made['key']), execute, lines.append) is False
    assert lines[0].startswith('FAIL') and 'refused the key' in lines[0]
    assert 'FAIL the monitoring plugin: LibreNMS answered 401 (LIBRENMS_URL and LIBRENMS_TOKEN are not set)' in lines
    assert any('no inventory plugin' in x for x in lines) and lines[-1].startswith('Fix')


def test_main_knows_its_commands():
    assert agent_mod.main(['delete-everything']) == 2


def _two_halls_two_agents(client, app_module):
    """Hall 1 (main) with sw-a-01, hall 2 with sw-h2-01, and an agent for each hall."""
    from floorbit import inventory, store
    hall2 = client.post('/api/halls', json={'name': 'Hall 2'}).get_json()['id']
    data = store.load_data()
    inventory.create(data, {'name': 'sw-a-01', 'role': 'switch'})
    dev = inventory.create(data, {'name': 'sw-h2-01', 'role': 'switch'})
    dev['hall_id'] = hall2
    store.save_data(data)
    main = client.get('/api/halls').get_json()['halls'][0]['id']
    one, two = enrol(client, 'Hall 1 agent'), enrol(client, 'Hall 2 agent')
    assert client.patch(f"/api/agents/{one['id']}", json={'halls': [main]}).status_code == 200
    assert client.patch(f"/api/agents/{two['id']}", json={'halls': [hall2]}).get_json()['halls'] == [hall2]
    return one, two


def test_calls_go_to_the_agent_for_the_hall(client, app_module):
    one, two = _two_halls_two_agents(client, app_module)
    assert client.patch(f"/api/agents/{one['id']}", json={'halls': ['nope']}).status_code == 400
    assert client.patch('/api/agents/00000000', json={'halls': []}).status_code == 404

    def site(name, switch):
        def execute(method, args):
            if method == 'devices':
                return [{'hostname': switch, 'status': 1}]
            if method == 'device_details':
                return {'status': 'online', 'hostname': args[0], 'answered_by': name}
            if method == 'resolve_ip':
                return {'device': switch} if name == 'two' else None
            raise RuntimeError('not here')
        return execute

    agents = [make(app_module, one['key'], site('one', 'sw-a-01')),
              make(app_module, two['key'], site('two', 'sw-h2-01'))]
    workers = []
    for a in agents:
        a.poll_wait = 0.5
        workers.append(threading.Thread(target=a.run, daemon=True))
        workers[-1].start()
    try:
        deadline = time.time() + 5
        while len(agent_link.tunnel.connected_agents()) < 2 and time.time() < deadline:
            time.sleep(0.05)
        mon = sources.monitoring()
        for _ in range(4):      # whichever agent polls first, the hall decides
            assert mon.device_details('sw-a-01')['answered_by'] == 'one'
            assert mon.device_details('sw-h2-01.example.com')['answered_by'] == 'two'
        assert sorted(d['hostname'] for d in mon.devices()) == ['sw-a-01', 'sw-h2-01']   # both sites
        assert mon.resolve_ip('192.0.2.20') == {'device': 'sw-h2-01'}                     # the one that knows
        listed = {a['name']: a for a in client.get('/api/agents').get_json()['agents']}
        assert listed['Hall 2 agent']['halls'] and listed['Hall 2 agent']['stats']['calls'] >= 4
    finally:
        for a in agents:
            a.stop()
        for w in workers:
            w.join(30)


def test_each_sites_netbox_keeps_its_own_devices(client, app_module):
    """With agents per hall, two NetBox servers sync under their own ids and don't mark each
    other's devices gone."""
    one, two = _two_halls_two_agents(client, app_module)

    def feeds(switch):
        def execute(method, args):
            if method == 'inventory_feeds':
                items = [{'id': '1', 'name': switch, 'role': 'switch'}]
                return [{'plugin': 'netbox', 'name': 'NetBox', 'items': items}]
            return []
        return execute

    agents = [make(app_module, one['key'], feeds('nb-a-01')), make(app_module, two['key'], feeds('nb-h2-01'))]
    workers = []
    for a in agents:
        a.poll_wait = 0.5
        workers.append(threading.Thread(target=a.run, daemon=True))
        workers[-1].start()
    try:
        deadline = time.time() + 5
        while len(agent_link.tunnel.connected_agents()) < 2 and time.time() < deadline:
            time.sleep(0.05)
        for _ in range(2):
            reports = client.post('/api/inventory/sync').get_json()['reports']
        mine = sorted(r['plugin'] for r in reports if r.get('via') == 'agent')
        assert mine == sorted([f"netbox.{one['id']}", f"netbox.{two['id']}"])
        assert all(r['gone'] == 0 and not r.get('error') for r in reports if r.get('via') == 'agent')
        assert not [r for r in reports if r['plugin'] == 'netbox']        # the hosted NetBox isn't asked
        names = {d['name'] for d in client.get('/api/inventory').get_json()['devices']}
        assert {'nb-a-01', 'nb-h2-01'} <= names
    finally:
        for a in agents:
            a.stop()
        for w in workers:
            w.join(30)


def test_health_checks_run_on_the_agent(client, app_module):
    """The health wall shows the agent's HTTP checks, made from the event network."""
    wall = app_module.app.extensions['floorbit_health']
    wall.stop()
    wall.reset()
    key = enrol(client)['key']

    def execute(method, args):
        if method == 'health_feeds':
            return [{'plugin': 'http-check', 'name': 'HTTP check', 'items': [
                {'id': 'cache', 'name': 'Cache', 'kind': 'cache', 'status': 'up', 'summary': '200 in 12 ms'}]}]
        return fake_execute(method, args)

    a = make(app_module, key, execute)
    a.poll_wait = 0.5
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        wall.poll_once()
        checks = {c['id']: c for c in wall.snapshot()['checks']}
        assert checks['http-check:cache']['status'] == 'up'
        assert checks['http-check:cache']['plugin_name'] == 'HTTP check (local agent)'
    finally:
        a.stop()
        worker.join(30)
        wall.reset()
    # Away: one grey tile that says so, not silently missing services.
    agent_link.tunnel.reset()
    wall.poll_once()
    assert [c['id'] for c in wall.snapshot()['checks']] == ['agent:*']
    wall.reset()


def test_the_agent_turns_plugins_on(app_module):
    from floorbit import sources as srcs
    said = []
    agent_mod.turn_on(app_module.app, 'http-check, no-such-plugin', said.append)
    with app_module.app.app_context():
        assert srcs.registry.enabled(srcs.registry.specs['http-check'])
    assert len(said) == 1 and 'no-such-plugin' in said[0]


def test_dns_lookups_come_through_the_agent_without_addresses(client, app_module, tmp_path):
    """The agent sends lookups with hashed clients and names cut to the site; the hosted stats count them."""
    from floorbit import dns

    class Spec:
        def __init__(self, i):
            self.id, self.name = i, 'Pi-hole'

    now = time.time()

    class Registry:
        def feeders(self, area):
            return [Spec('pihole')] if area == 'dns' else []

        def call(self, spec, method, since):
            return [{'ts': now - 5, 'domain': 'cdn.steamcontent.example', 'client': f'198.51.100.{i}', 'blocked': False}
                    for i in range(6)] + [{'ts': now - 5, 'domain': 'gamer-pc.lan', 'client': '198.51.100.9'}]

    sent = agent_mod.dns_feeds(Registry(), now - 60)[0]['items']
    assert {e['domain'] for e in sent} == {'steamcontent.example', None}       # the machine name stays home
    assert not any('198.51.100' in str(e) for e in sent)                         # so do the addresses
    assert len({e['client'] for e in sent}) == 7                                 # but distinct clients still count

    key = enrol(client)['key']
    a = make(app_module, key, lambda method, args: agent_mod.dns_feeds(Registry(), *args)
             if method == 'dns_feeds' else fake_execute(method, args))
    a.poll_wait = 0.5
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        stats = dns.DnsStats(path=str(tmp_path / 'dns.json'))
        stats.registry = None
        stats.poll_once(now=now)
        stats.poll_once(now=now + 1)                     # the cursor keeps it from counting twice
        stats.add([], now=now + 3600)                    # close the hour
        snap = stats.snapshot(hours=2, now=now + 3600)
        assert snap['lookups'] == 7 and snap['plugins'] == 1 and snap['error'] is None
        assert 'steamcontent.example' in [s['site'] for s in snap['sites']]   # 6 clients: named
    finally:
        a.stop()
        worker.join(30)


def test_wifi_comes_through_the_agent_as_counts_only(client, app_module):
    from floorbit import wifi
    wifi.reset()

    class Spec:
        id, name = 'unifi', 'UniFi'

    class Registry:
        def feeders(self, area):
            return [Spec()] if area == 'wifi' else []

        def call(self, spec, method):
            return [{'name': 'ap-hall-01', 'model': 'U6-Pro', 'status': 'up',
                     'clients_list': [{'hostname': 'gamer-laptop', 'mac': '02:00:00:00:00:01'}],
                     'radios': [{'band': '5', 'channel': 36, 'width': 80, 'utilization': 42, 'clients': 18}]}]

    sent = agent_mod.wifi_feeds(Registry())[0]['items']
    assert sent[0]['clients'] == 18 and 'gamer-laptop' not in str(sent) and '02:00' not in str(sent)

    key = enrol(client)['key']
    a = make(app_module, key, lambda method, args: agent_mod.wifi_feeds(Registry())
             if method == 'wifi_feeds' else fake_execute(method, args))
    a.poll_wait = 0.5
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        body = client.get('/api/wifi').get_json()
        assert [ap['name'] for ap in body['aps']] == ['ap-hall-01'] and body['clients'] == 18
        assert body['aps'][0]['source'] == 'UniFi (local agent)' and 'Local agent' in body['sources']
    finally:
        a.stop()
        worker.join(30)
        wifi.reset()


def _syslog_receiver(app_module, monkeypatch):
    from floorbit import syslog
    receiver = app_module.app.extensions["floorbit_syslog"]
    monkeypatch.setattr(receiver, "lines", syslog.deque())
    monkeypatch.setattr(receiver, "relayed", {})
    monkeypatch.setattr(receiver, "_buckets", {})
    receiver._allow_cache = (time.time() + 3600, [syslog.ipaddress.ip_network("192.0.2.0/24")], {})
    return receiver


def test_syslog_comes_through_the_agent(client, app_module, monkeypatch):
    from floorbit.agent.syslog_relay import Relay
    receiver = _syslog_receiver(app_module, monkeypatch)
    a = make(app_module, enrol(client)["key"])
    relay = Relay(a.send_syslog, 0, log=lambda *_: None)
    started = time.time() - 120
    relay.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/4, changed state to down\n", "192.0.2.9", now=started)
    relay.receive(b"<190>dhcpd: DHCPACK on 192.0.2.40", "192.0.2.10")
    relay.receive(b"<190>from outside the allow-list", "203.0.113.7")
    relay.receive(b"   ", "192.0.2.9")                       # nothing to send
    assert relay.flush_once() == 3 and not relay.lines
    kept = list(receiver.lines)
    assert [ln["message"] for ln in kept] == ["Interface Gi1/0/4, changed state to down", "DHCPACK on 192.0.2.40"]
    assert kept[0]["sender"] == "192.0.2.9" and kept[0]["ts"] == pytest.approx(started)   # when the agent got it
    assert receiver.counts["not_allowed"] >= 1
    status = client.get("/api/logs").get_json()["status"]
    assert status["relayed"][0]["agent"] == "Demo LAN 2026" and status["relayed"][0]["lines"] == 2


def test_the_agent_keeps_syslog_while_the_host_is_away():
    from floorbit.agent.syslog_relay import Relay
    sent, up = [], {"ok": False}

    def send(lines, dropped):
        if not up["ok"]:
            raise RuntimeError("no route to host")
        sent.append((len(lines), dropped))

    relay = Relay(send, 0, backlog=3, log=lambda *_: None)
    for n in range(5):
        relay.receive(f"<14>line {n}".encode(), "192.0.2.9")
    with pytest.raises(RuntimeError):
        relay.flush_once()
    assert [ln["raw"] for ln in relay.lines] == ["<14>line 0", "<14>line 1", "<14>line 2"]   # the newest went
    up["ok"] = True
    assert relay.flush_once() == 3 and sent == [(3, 2)] and relay.sent == 3


def test_the_host_says_when_syslog_is_off(client, app_module, monkeypatch):
    from floorbit.agent.syslog_relay import Relay, TurnedOff
    _syslog_receiver(app_module, monkeypatch)
    a = make(app_module, enrol(client)["key"])
    assert client.put("/api/settings/features", json={"syslog": False}).status_code == 200
    relay = Relay(a.send_syslog, 0, log=lambda *_: None)
    relay.receive(b"<14>hello", "192.0.2.9")
    with pytest.raises(TurnedOff):
        relay.flush_once()
    assert not relay.lines                                    # not kept: they'd only fill the backlog
    anon = app_module.app.test_client()
    assert anon.post("/api/agent/v1/syslog", json={"lines": []}).status_code == 401


def test_odd_relayed_lines_are_skipped(client, app_module, monkeypatch):
    receiver = _syslog_receiver(app_module, monkeypatch)
    key = enrol(client)["key"]
    lines = [{"raw": "<14>fine", "from": "192.0.2.9", "at": "soon"}, {"raw": 5, "from": "192.0.2.9"},
             {"raw": "<14>no sender"}, {"raw": "<14>bad sender", "from": "sw-a-01"}, "text",
             {"raw": "<14>from the future", "from": "192.0.2.9", "at": time.time() + 9999}]
    res = app_module.app.test_client().post("/api/agent/v1/syslog", json={"lines": lines, "dropped": "x"},
                                            headers={"Floorbit-Agent-Key": key})
    assert res.get_json() == {"taken": 2, "received": 6}
    assert all(ln["ts"] <= time.time() for ln in receiver.lines)


def test_the_relay_listens_on_udp(client, app_module, monkeypatch):
    import ipaddress
    import socket
    receiver = _syslog_receiver(app_module, monkeypatch)
    receiver._allow_cache = (time.time() + 3600, [ipaddress.ip_network("127.0.0.1/32")], {})
    a = make(app_module, enrol(client)["key"])
    monkeypatch.setenv("FLOORBIT_AGENT_SYSLOG_BIND", "127.0.0.1")
    assert agent_mod.start_syslog(a, "") is None
    assert agent_mod.start_syslog(a, "not a port", out=lambda *_: None) is False
    relay = agent_mod.start_syslog(a, "0", out=lambda *_: None)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(b"<14>hello over the agent", ("127.0.0.1", relay._server.server_address[1]))
        deadline = time.time() + 5
        while not receiver.lines and time.time() < deadline:
            time.sleep(0.05)
        assert receiver.lines and receiver.lines[-1]["message"] == "hello over the agent"
    finally:
        relay.stop()


def test_flows_are_counted_on_the_agent_and_only_the_summary_goes_up(client, app_module, monkeypatch, tmp_path):
    import floorbit.flows as flows_pkg
    from floorbit.agent.flows_relay import FlowsRelay
    from floorbit.flows import store
    from floorbit.flows.aggregate import Aggregator
    from floorbit.flows.classify import Classifier
    from floorbit.flows.collector import Collector
    from tests.test_flows import NOW, STEAM, v5
    monkeypatch.setattr(flows_pkg, "seat_maps", lambda: ({"192.0.2.10": "A-1"}, {"A-1": "A"}))
    a = make(app_module, enrol(client)["key"])
    sent = []
    collector = Collector(Aggregator(Classifier()), store.RawStore(str(tmp_path)), log=lambda *_: None)
    relay = FlowsRelay(a, 0, collector=collector, log=lambda *_: None)
    real_send = a.send_flows
    monkeypatch.setattr(a, "send_flows", lambda snap: (sent.append(snap), real_send(snap))[1])
    relay.tick(now=NOW)                                      # the seats come from the hosted Floorbit
    assert collector.agg.seat_of == {"192.0.2.10": "A-1"}
    collector.receive(v5([STEAM]), "198.51.100.1", now=NOW + 1)
    collector._next["publish"] = 0
    relay.tick(now=NOW + 2)
    assert relay.sent == 2 and sent[-1]["mix_hour"] == {"gaming": 5_000_000}
    body = client.get("/api/flows").get_json()
    assert body["collector"] and body["agent"] == "Demo LAN 2026" and body["mix_hour"] == {"gaming": 5_000_000}
    assert body["seats"][0]["seat"] == "A-1" and not body["stale"]
    assert "192.0.2.10" not in str(body) and "203.0.113.30" not in str(body)
    assert len(os.listdir(tmp_path / "raw")) == 1            # the flow records stay on the agent


def test_flows_need_traffic_on_and_a_snapshot(client, app_module):
    key = enrol(client)["key"]
    agent = app_module.app.test_client()
    h = {"Floorbit-Agent-Key": key}
    assert agent.post("/api/agent/v1/flows", json={"snapshot": "x"}, headers=h).status_code == 400
    assert agent.post("/api/agent/v1/flows", json={}, headers=h).status_code == 400
    assert agent.get("/api/agent/v1/seats").status_code == 401
    assert client.put("/api/settings/features", json={"traffic": False}).status_code == 200
    assert agent.get("/api/agent/v1/seats", headers=h).status_code == 409
    assert agent.post("/api/agent/v1/flows", json={"snapshot": {"updated": 1}}, headers=h).status_code == 409


def test_a_failing_summary_is_logged_once(app_module):
    from floorbit.agent.flows_relay import FlowsRelay

    class Away:
        def send_flows(self, snap):
            raise RuntimeError("no route to host")

    said = []
    relay = FlowsRelay(Away(), 0, log=said.append)
    assert relay._publish({}) is False and relay._publish({}) is False
    assert len(said) == 1 and "no route to host" in said[0]


def test_the_agent_starts_its_flow_collector(client, app_module, monkeypatch):
    a = make(app_module, enrol(client)["key"])
    monkeypatch.setenv("FLOORBIT_AGENT_FLOWS_BIND", "127.0.0.1")
    assert agent_mod.start_flows(a, "") is None
    assert agent_mod.start_flows(a, "x", out=lambda *_: None) is False
    relay = agent_mod.start_flows(a, "0", out=lambda *_: None)
    try:
        assert relay._sock is not None
    finally:
        relay.stop()
    assert relay._sock is None


def test_without_redis_the_agents_summary_is_kept_in_memory(monkeypatch):
    from floorbit import cache
    from floorbit.flows import store
    monkeypatch.setattr(cache, "get_redis_client", lambda: None)
    monkeypatch.setattr(store, "_local", {"at": 0, "snapshot": None})
    assert store.publish({"updated": 1}) is False and store.latest() is None   # the collector needs Redis
    assert store.publish({"updated": 1}, keep_locally=True) and store.latest() == {"updated": 1}
    store._local["at"] -= store.SNAPSHOT_TTL + 1
    assert store.latest() is None


def test_check_tries_syslog_and_flows_when_set(client, app_module, monkeypatch):
    import floorbit.flows as flows_pkg
    monkeypatch.setattr(flows_pkg, "seat_maps", lambda: ({"192.0.2.10": "A-1"}, {"A-1": "A"}))
    monkeypatch.setenv("FLOORBIT_AGENT_SYSLOG_PORT", "5514")
    monkeypatch.setenv("FLOORBIT_AGENT_FLOWS_PORT", "2055")
    a = make(app_module, enrol(client)["key"])

    def execute(method, args):
        return [] if method in ("inventory_feeds", "health_feeds") else fake_execute(method, args)

    lines = []
    assert agent_mod.check(a, execute, lines.append) is True
    assert any(x.startswith("OK   the hosted Floorbit takes syslog") and "UDP 5514" in x for x in lines)
    assert any(x.startswith("OK   the hosted Floorbit takes flows and knows 1 seat") for x in lines)
    assert client.get("/api/logs").get_json()["status"]["relayed"] == []   # a check isn't an agent sending
    assert client.put("/api/settings/features", json={"syslog": False, "traffic": False}).status_code == 200
    lines.clear()
    assert agent_mod.check(a, execute, lines.append) is False
    assert any(x.startswith("FAIL syslog: Syslog is turned off") for x in lines)
    assert any(x.startswith("FAIL flows: Traffic is turned off") for x in lines)


def test_stopping_sends_the_syslog_backlog():
    from floorbit.agent.syslog_relay import Relay
    sent = []
    relay = Relay(lambda lines, dropped: sent.extend(lines), 0, log=lambda *_: None)
    relay.receive(b"<14>last words", "192.0.2.9")
    relay.stop()
    assert [x["raw"] for x in sent] == ["<14>last words"] and not relay.lines

    said = []

    def down(lines, dropped):
        raise RuntimeError("no route to host")

    relay = Relay(down, 0, log=said.append)
    relay.receive(b"<14>lost", "192.0.2.9")
    relay.stop()
    assert said == ["[agent] 1 syslog lines could not be sent before stopping: no route to host"]


def test_sigterm_stops_like_ctrl_c():
    with pytest.raises(KeyboardInterrupt):
        agent_mod._stop_on_term(15, None)
