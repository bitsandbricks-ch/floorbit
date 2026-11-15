"""The local agent program (issue #2) against the hosted side, all in one process.

The agent's HTTP goes through the Flask test client, so nothing leaves the process."""
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
    assert agent_mod.main() == 2
    monkeypatch.setenv('FLOORBIT_URL', 'http://hosted.example.com')
    monkeypatch.setenv('FLOORBIT_AGENT_KEY', 'fba_00000000_' + 'x' * 30)
    monkeypatch.delenv('FLOORBIT_AGENT_INSECURE', raising=False)
    assert agent_mod.main() == 2
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
