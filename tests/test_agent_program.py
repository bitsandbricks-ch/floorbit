"""The local agent program (issue #2) against the hosted side, all in one process.

The agent is bitsandbricks-ch/floorbit-agent at the commit in AGENT_REF (tests/conftest.py puts it
on the path). Its HTTP goes through the Flask test client, so nothing leaves the process."""
import os
import threading
import time

import pytest

try:
    import floorbit_agent as agent_mod
except ImportError as exc:     # fail loudly: a skipped hosted side would look green
    raise ImportError('These tests run the agent from bitsandbricks-ch/floorbit-agent: clone it next to this '
                      'repository (at the commit in AGENT_REF) or set FLOORBIT_AGENT_SRC.') from exc
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
    if method == 'configured':     # an agent with LibreNMS set up
        return True
    if method == 'devices':
        return [{'hostname': 'sw-a-01', 'status': 1}]
    if method == 'device_details':
        return {'status': 'online', 'hostname': args[0]}
    raise RuntimeError('LibreNMS said no')


def make(app_module, key, execute=fake_execute):
    a = agent_mod.Agent('http://hosted.example.com/', key, execute,
                        http=ClientHttp(app_module.app.test_client()), version='9.9.9', log=lambda *_: None)
    # The test client can't open a WebSocket (tests/test_agent.py tries the link on a real port):
    # these run the long poll, which takes the same calls.
    a.link_after = float('inf')
    return a


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
    # NetBox is on by default but not set up here: it isn't asked, so no "set up NetBox" error
    # reads as a failed import (issue #1169).
    assert feeds == []


def test_the_agent_sends_a_set_up_cable_plugin_and_its_error(app_module, monkeypatch):
    from floorbit.plugins.base import PluginError

    def cables(self):
        raise PluginError('NetBox is down')
    # The class the registry loaded (plugin.py is imported under its own module name).
    cls = app_module.app.extensions['floorbit_plugins'].specs['netbox'].plugin_class()
    monkeypatch.setattr(cls, 'configured', lambda self: True)
    monkeypatch.setattr(cls, 'cables', cables)
    with app_module.app.app_context():
        from floorbit import sources as srcs
        feeds = agent_mod.cable_feeds(srcs.registry)
    # Set up but failing: it is asked, and its error comes back, not an exception.
    assert [f['plugin'] for f in feeds] == ['netbox'] and feeds[0]['error']


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


def test_check_names_what_fails(client, app_module):
    made = enrol(client)
    client.delete(f"/api/agents/{made['id']}")
    lines = []

    def execute(method, args):
        if method in ('inventory_feeds', 'health_feeds'):
            return []
        raise RuntimeError('LibreNMS answered 401')

    assert agent_mod.check(make(app_module, made['key']), execute, lines.append) is False
    assert ('FAIL the monitoring plugin: LibreNMS answered 401 (set it up in Settings > Plugins on the hosted '
            'Floorbit)') in lines
    assert lines[0].startswith('FAIL') and 'refused the key' in lines[0]
    assert any('no inventory plugin' in x for x in lines) and lines[-1].startswith('Fix')


def test_main_knows_its_commands():
    assert agent_mod.main(['delete-everything']) == 2


def _two_halls_two_agents(client, app_module):
    """Two sites as inventory tags (issue #869): sw-a-01 tagged "Site A" itself, sw-h2-01 in a group
    that carries "Site B", and an agent for each tag."""
    from floorbit import inventory, store
    site_a = client.post('/api/inventory/tags', json={'name': 'Site A'}).get_json()['id']
    site_b = client.post('/api/inventory/tags', json={'name': 'Site B'}).get_json()['id']
    group = client.post('/api/inventory/groups', json={'name': 'Hall 2', 'tags': [site_b]}).get_json()['id']
    data = store.load_data()
    dev = inventory.create(data, {'name': 'sw-a-01', 'role': 'switch'})
    dev['tags'] = [site_a]
    dev = inventory.create(data, {'name': 'sw-h2-01', 'role': 'switch'})
    dev['group_id'] = group
    store.save_data(data)
    one, two = enrol(client, 'Hall 1 agent'), enrol(client, 'Hall 2 agent')
    assert client.patch(f"/api/agents/{one['id']}", json={'tags': [site_a]}).status_code == 200
    assert client.patch(f"/api/agents/{two['id']}", json={'tags': [site_b]}).get_json()['tags'] == [site_b]
    return one, two


def test_calls_go_to_the_agent_for_the_devices_tags(client, app_module):
    one, two = _two_halls_two_agents(client, app_module)
    assert client.patch(f"/api/agents/{one['id']}", json={'tags': ['nope']}).status_code == 400
    assert client.patch('/api/agents/00000000', json={'tags': []}).status_code == 404

    def site(name, switch):
        def execute(method, args):
            if method == 'configured':
                return True
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
        for _ in range(4):      # whichever agent polls first, the tags decide (one through its group)
            assert mon.device_details('sw-a-01')['answered_by'] == 'one'
            assert mon.device_details('sw-h2-01.example.com')['answered_by'] == 'two'
        assert sorted(d['hostname'] for d in mon.devices()) == ['sw-a-01', 'sw-h2-01']   # both sites
        assert mon.resolve_ip('192.0.2.20') == {'device': 'sw-h2-01'}                     # the one that knows
        listed = {a['name']: a for a in client.get('/api/agents').get_json()['agents']}
        assert listed['Hall 2 agent']['tags'] and listed['Hall 2 agent']['stats']['calls'] >= 4
    finally:
        for a in agents:
            a.stop()
        for w in workers:
            w.join(30)


def test_two_agents_for_the_same_tags_answer_from_the_primary(client, app_module):
    """Agents sharing VIPs (VRRP): only the primary has the telemetry picture; the standby's empty
    answers never win, and lists come once."""
    one, two = enrol(client, 'Agent A'), enrol(client, 'Agent B')

    def site(primary):
        def execute(method, args):
            if method == 'configured':
                return True
            if method == 'devices':
                return [{'hostname': 'sw-a-01', 'status': 1}] if primary else []
            if method == 'device_ports':
                return [{'name': 'Gi1/0/1'}] if primary else []
            if method == 'arp':
                return [{'ipv4_address': '192.0.2.40', 'mac_address': '020000000007', 'hostname': 'core'}]
            raise RuntimeError('not here')
        return execute

    agents = [make(app_module, one['key'], site(False)), make(app_module, two['key'], site(True))]
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
        for _ in range(4):      # whichever agent polls first
            assert [d['hostname'] for d in mon.devices()] == ['sw-a-01']
            assert mon.device_ports('sw-a-01') == [{'name': 'Gi1/0/1'}]
        assert len(agent_link.ask('arp', ('192.0.2.40',))) == 1      # the same row from both, once
    finally:
        for a in agents:
            a.stop()
        for w in workers:
            w.join(30)


def test_each_sites_netbox_keeps_its_own_devices(client, app_module):
    """With agents per site (tag), two NetBox servers sync under their own ids and don't mark each
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
        # The app's own DNS watcher polls the connected agent too; left running, it would write these
        # lookups into the shared database while later tests run (#1639).
        watcher = app_module.app.extensions['floorbit_dns']
        watcher.stop()
        if watcher._thread is not None:
            watcher._thread.join(10)
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


class _OldAgent:
    """An agent from before syslog and flows were plugins: it posts to the hosted side's own
    endpoints, which stay for it (floorbit/blueprints/agent.py)."""

    def __init__(self, agent):
        self.a = agent

    def send_syslog(self, lines, dropped=0):
        from floorbit_agent.syslog_relay import TurnedOff
        resp = self.a._post('/api/agent/v1/syslog', {'lines': lines, 'dropped': dropped})
        if resp.status_code == 409:
            raise TurnedOff(resp.json().get('error'))
        return self.a._check(resp)

    def _said(self, resp):
        if resp.status_code == 409:
            raise RuntimeError(resp.json().get('error'))
        return self.a._check(resp)

    def flow_seats(self):
        return self._said(self.a.http.get(f'{self.a.url}/api/agent/v1/seats', headers=self.a._headers()))

    def send_flows(self, snapshot):
        return self._said(self.a._post('/api/agent/v1/flows', {'snapshot': snapshot}))


def _syslog_receiver(app_module, monkeypatch):
    from floorbit import syslog
    receiver = app_module.app.extensions["floorbit_syslog"]
    monkeypatch.setattr(receiver, "lines", syslog.deque())
    monkeypatch.setattr(receiver, "relayed", {})
    monkeypatch.setattr(receiver, "_buckets", {})
    receiver._allow_cache = (time.monotonic() + 3600, [syslog.ipaddress.ip_network("192.0.2.0/24")], {})
    return receiver


def test_syslog_comes_through_the_agent(client, app_module, monkeypatch):
    from floorbit_agent.syslog_relay import Relay
    receiver = _syslog_receiver(app_module, monkeypatch)
    a = _OldAgent(make(app_module, enrol(client)["key"]))
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
    from floorbit_agent.syslog_relay import Relay
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
    from floorbit_agent.syslog_relay import Relay, TurnedOff
    _syslog_receiver(app_module, monkeypatch)
    a = _OldAgent(make(app_module, enrol(client)["key"]))
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



def test_flows_are_counted_on_the_agent_and_only_the_summary_goes_up(client, app_module, monkeypatch, tmp_path):
    from floorbit_agent.flows_relay import FlowsRelay

    import floorbit.flows as flows_pkg
    from floorbit.flows import store
    from floorbit.flows.aggregate import Aggregator
    from floorbit.flows.classify import Classifier
    from floorbit.flows.collector import Collector
    from tests.test_flows import NOW, STEAM, v5
    monkeypatch.setattr(flows_pkg, "seat_maps", lambda: ({"192.0.2.10": "A-1"}, {"A-1": "A"}))
    a = _OldAgent(make(app_module, enrol(client)["key"]))
    sent = []
    collector = Collector(Aggregator(Classifier()), store.RawStore(str(tmp_path)), log=lambda *_: None)
    relay = FlowsRelay(a, 0, collector=collector, log=lambda *_: None)
    real_send = a.send_flows
    monkeypatch.setattr(a, "send_flows", lambda snap: (sent.append(snap), real_send(snap))[1])
    relay.tick(now=NOW)                                      # the seats come from the hosted Floorbit
    assert collector.agg.seat_of == {"192.0.2.10": "A-1"}
    collector.receive(v5([STEAM]), "198.51.100.1", now=NOW + 1)
    collector._next["publish"] = collector._next["raw"] = 0
    relay.tick(now=NOW + 200)                                # the minute is closed: its rows go to disk
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



def test_a_summary_of_the_wrong_shape_cannot_break_the_traffic_page(client, app_module):
    # Before: anomalies that weren't {"id", "kind", ...} made /api/flows a 500 for everyone.
    key = enrol(client)["key"]
    agent = app_module.app.test_client()
    good = {"id": "p2p:192.0.2.10", "kind": "p2p", "seat": "A-1", "first_seen": 1, "last_seen": 2,
            "title": "P2P", "detail": "many peers"}
    snap = {"updated": 1, "anomalies": [5, {"id": 3}, {"kind": "x"}, good], "seats": "s", "services": 5,
            "series": {"a": 1}, "mix_hour": [1], "flows": "many", "errors": True}
    h = {"Floorbit-Agent-Key": key}
    assert agent.post("/api/agent/v1/flows", json={"snapshot": snap}, headers=h).status_code == 200
    for lang in ("en", "de"):
        got = client.get("/api/flows", headers={"Accept-Language": lang})
        assert got.status_code == 200
        body = got.get_json()
        assert [a["kind"] for a in body["anomalies"]] == ["p2p"]
        # Wrong shapes come out empty (or not at all), never as something a page can't add up.
        assert not any(body.get(k) for k in ("services", "series", "mix_hour"))
        assert not isinstance(body.get("flows"), (list, dict)) and not isinstance(body.get("errors"), (list, dict))
    assert agent.post("/api/agent/v1/flows", json={"snapshot": {"updated": 1, "anomalies": "x"}},
                      headers=h).status_code == 200
    assert client.get("/api/flows").status_code == 200

def test_a_failing_summary_is_logged_once(app_module):
    from floorbit_agent.flows_relay import FlowsRelay

    class Away:
        def send_flows(self, snap):
            raise RuntimeError("no route to host")

    said = []
    relay = FlowsRelay(Away(), 0, log=said.append)
    assert relay._publish({}) is False and relay._publish({}) is False
    assert len(said) == 1 and "no route to host" in said[0]



def test_the_agents_summary_is_kept_in_the_database_without_redis(monkeypatch):
    from floorbit import cache
    from floorbit import store as docs
    from floorbit.flows import store
    monkeypatch.setattr(cache, "get_redis_client", lambda: None)
    assert store.latest() is None
    assert store.publish({"updated": 1}) and store.latest() == {"updated": 1}
    path = docs.event_path(store.SUMMARY_FILE)
    saved = docs.read_json(path, {})
    docs.write_json(path, {**saved, "at": saved["at"] - store.SNAPSHOT_TTL - 1})
    assert store.latest() is None



def test_stopping_sends_the_syslog_backlog():
    from floorbit_agent.syslog_relay import Relay
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


def test_the_agents_page_shows_what_each_agent_relays(client, app_module, monkeypatch):
    _syslog_receiver(app_module, monkeypatch)
    first, second = enrol(client, "Hall 1"), enrol(client, "Hall 2")
    agent = app_module.app.test_client()
    lines = [{"raw": "<14>hello", "from": "192.0.2.9"}, {"raw": "<14>outside", "from": "203.0.113.7"}]
    agent.post("/api/agent/v1/syslog", json={"lines": lines}, headers={"Floorbit-Agent-Key": first["key"]})
    agent.post("/api/agent/v1/syslog", json={"lines": []}, headers={"Floorbit-Agent-Key": second["key"]})  # a check
    agent.post("/api/agent/v1/flows", json={"snapshot": {"updated": 1}}, headers={"Floorbit-Agent-Key": second["key"]})
    shown = {a["name"]: a["relays"] for a in client.get("/api/agents").get_json()["agents"]}
    assert shown["Hall 1"]["syslog"]["count"] == 1 and "flows" not in shown["Hall 1"]
    assert list(shown["Hall 2"]) == ["flows"]
    later = time.time() + agent_link.RELAY_RECENT + 1
    assert agent_link.tunnel.relays(first["id"], now=later) == {}


def test_health_says_whether_the_host_answered_lately(tmp_path):
    beat = tmp_path / "agent-heartbeat"
    said = []
    assert agent_mod.health(str(beat), out=said.append) == 1 and "not reached" in said[-1]
    a = agent_mod.Agent("http://hosted.example.com", "fba_x_y", fake_execute, http=object(), log=said.append)
    a.heartbeat = str(beat)
    a.beat(now=1000)
    assert beat.read_text() == "1000\n"
    assert agent_mod.health(str(beat), out=said.append) == 0 and said[-1].startswith("healthy")
    later = os.path.getmtime(beat) + agent_mod.HEALTHY_FOR + 5
    assert agent_mod.health(str(beat), now=later, out=said.append) == 1 and "last answered" in said[-1]
    beat.write_text("")
    a.beat(now=1005)                                    # too soon: not written again
    assert beat.read_text() == ""
    a.heartbeat = str(tmp_path / "missing" / "beat")
    a.beat(now=2000)
    # The agent keeps trying (a full disk can pass) and says so once, not on every beat.
    assert a.heartbeat and "cannot write the heartbeat" in said[-1]
    told = len(said)
    a.beat(now=2000 + agent_mod.BEAT_EVERY)
    assert len(said) == told


def test_a_poll_that_gets_through_beats(client, app_module, tmp_path):
    a = make(app_module, enrol(client)["key"])
    a.heartbeat = str(tmp_path / "beat")
    a.poll_wait = 0.2
    worker = threading.Thread(target=a.run, daemon=True)
    worker.start()
    try:
        deadline = time.time() + 5
        while not os.path.exists(a.heartbeat) and time.time() < deadline:
            time.sleep(0.05)
        assert agent_mod.health(a.heartbeat, out=lambda *_: None) == 0
    finally:
        a.stop()
        worker.join(5)


def test_main_health_needs_no_settings(monkeypatch, tmp_path):
    monkeypatch.delenv("FLOORBIT_URL", raising=False)
    monkeypatch.setenv("FLOORBIT_AGENT_HEARTBEAT", str(tmp_path / "beat"))
    assert agent_mod.main(["health"]) == 1
    (tmp_path / "beat").write_text("1\n")
    assert agent_mod.main(["health"]) == 0


def test_big_bodies_go_gzipped_once_the_host_says_it_takes_them(client, app_module, monkeypatch):
    receiver = _syslog_receiver(app_module, monkeypatch)
    a = make(app_module, enrol(client)["key"])
    old = _OldAgent(a)
    sent = []
    real_post = a.http.post
    monkeypatch.setattr(a.http, "post", lambda url, data=None, headers=None, timeout=None: (
        sent.append(dict(headers or {})), real_post(url, data=data, headers=headers))[1])
    lines = [{"raw": f"<14>line {n} " + "x" * 40, "from": "192.0.2.9", "at": time.time()} for n in range(100)]
    old.send_syslog(lines[:1])
    assert "Content-Encoding" not in sent[-1]                   # before hello: plain, any host takes that
    assert a.hello() and a.gzip
    old.send_syslog(lines)
    assert sent[-1]["Content-Encoding"] == "gzip" and len(receiver.lines) == 101
    old.send_syslog(lines[:1])
    assert "Content-Encoding" not in sent[-1]                   # too small to be worth it


def test_broken_or_huge_gzip_is_refused(client, app_module, monkeypatch):
    import gzip as gz

    from floorbit.blueprints import agent as agent_bp
    _syslog_receiver(app_module, monkeypatch)
    key = enrol(client)["key"]
    h = {"Floorbit-Agent-Key": key, "Content-Encoding": "gzip", "Content-Type": "application/json"}
    post = app_module.app.test_client().post
    # Refused out loud, not read as an empty batch the agent then counts as delivered.
    res = post("/api/agent/v1/syslog", data=b"not gzip", headers=h)
    assert res.status_code == 400 and "gzip" in res.get_json()["error"]
    monkeypatch.setattr(agent_bp, "MAX_UNZIPPED", 1000)
    bomb = gz.compress(b'{"lines": [' + b" " * 5000 + b"]}")
    res = post("/api/agent/v1/syslog", data=bomb, headers=h)
    assert res.status_code == 413 and "in parts" in res.get_json()["error"]
    plain = {"Floorbit-Agent-Key": key, "Content-Type": "application/json"}
    assert post("/api/agent/v1/syslog", data=b"{not json", headers=plain).status_code == 400
    assert post("/api/agent/v1/plugins/telemetry/points", data=b"[1]", headers=plain).status_code == 400
    fine = gz.compress(b'{"lines": [{"raw": "<14>hi", "from": "192.0.2.9"}]}')
    assert post("/api/agent/v1/syslog", data=fine, headers=h).get_json() == {"taken": 1, "received": 1}


def test_another_protocol_gets_one_clear_answer(client, app_module, monkeypatch):
    key = enrol(client)["key"]
    agent = app_module.app.test_client()
    h = {"Floorbit-Agent-Key": key}
    hello = agent.get("/api/agent/v1/hello", headers=h).get_json()        # no header: protocol 1
    assert hello["protocol"] == agent_link.PROTOCOL and agent_mod.PROTOCOL in hello["protocols"]
    res = agent.get("/api/agent/v1/calls?wait=0", headers={**h, "Floorbit-Agent-Protocol": "9"})
    assert res.status_code == 426 and "protocol 2, the agent 9" in res.get_json()["error"]
    assert client.get("/api/agents").status_code == 200                    # the admin side doesn't care
    a = make(app_module, key)
    a.hello()
    assert a.protocol == 2 and a.link_path == "/api/agent/v2/link"     # it moves up once hello says so
    # A Floorbit that no longer speaks the agent's first protocol: the agent stops instead of retrying.
    monkeypatch.setattr(agent_link, "PROTOCOLS", (2,))
    with pytest.raises(agent_mod.Refused, match="Update the agent"):
        make(app_module, key).run()


def test_a_skewed_agent_clock_is_corrected_from_its_header(client, app_module, monkeypatch):
    from floorbit import agent_clock
    receiver = _syslog_receiver(app_module, monkeypatch)
    key = enrol(client)["key"]
    now = time.time()
    day = 86400   # a box without a battery clock, a day behind: every line used to be past retention
    lines = [{"raw": "<14>%LINK-3-UPDOWN: Interface Gi1/0/3, changed state to down", "from": "192.0.2.9",
              "at": now - day}]
    post = app_module.app.test_client().post
    res = post("/api/agent/v1/syslog", json={"lines": lines}, headers={"Floorbit-Agent-Key": key})
    assert res.get_json()["taken"] == 0
    res = post("/api/agent/v1/syslog", json={"lines": lines},
               headers={"Floorbit-Agent-Key": key, agent_clock.HEADER: f"{now - day:.3f}"})
    assert res.get_json()["taken"] == 1
    assert abs(receiver.lines[-1]["ts"] - now) < 5
    for odd in ("soon", "nan", "inf", ""):      # nonsense is ignored, not trusted
        res = post("/api/agent/v1/syslog", json={"lines": lines},
                   headers={"Floorbit-Agent-Key": key, agent_clock.HEADER: odd})
        assert res.get_json()["taken"] == 0


def test_agent_tags_take_the_place_of_halls(app_module):
    """Issue #869: the upgrade drops the halls an agent was limited to (nothing is live yet)."""
    from floorbit import upgrades
    data = {'agents': [{'id': 'a1', 'name': 'A', 'halls': ['main']}],
            upgrades.KEY: upgrades.STEPS.index(upgrades._agent_tags)}
    assert upgrades.apply(data)
    assert 'halls' not in data['agents'][0]


def test_a_device_has_the_tags_its_groups_give_it(app_module):
    from floorbit import inventory_scope
    data = {'inventory_groups': [{'id': 'g1', 'name': 'Hall', 'tags': ['t1']},
                                 {'id': 'g2', 'name': 'Row', 'parent_id': 'g1', 'tags': ['t2']}]}
    assert inventory_scope.device_tags(data, {'tags': ['t3'], 'group_id': 'g2'}) == {'t1', 't2', 't3'}
    assert inventory_scope.device_tags(data, {}) == frozenset()
