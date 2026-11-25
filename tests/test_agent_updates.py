"""Updates of the agents themselves (floorbit-agent #98): the release this Floorbit fetches, who gets
it (one agent of an HA group at a time, the primary last), what the page shows and the audit log.
No network: the releases are a fake."""
import hashlib
import json

import pytest
from test_agent import clean_tunnel, enrol, head  # noqa: F401  # clean_tunnel is autouse there

from floorbit import agent_link, agent_updates, audit

IMAGE = '0123456789abcdef'
DATA = b'signed agent update'


def meta(version='1.5.0', image=IMAGE, protocol=2):
    return {'version': version, 'file': f'floorbit-agent-{version}.tar.gz',
            'sha256': hashlib.sha256(DATA).hexdigest(), 'image': image, 'protocol': protocol}


@pytest.fixture
def releases(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_updates, 'folder', lambda: tmp_path / 'agent-releases')
    asked = []

    def get(url, limit, timeout):
        asked.append(url)
        if url == agent_updates.RELEASE_URL:
            return json.dumps(get.meta).encode()
        return get.data
    get.meta, get.data, get.asked = meta(), DATA, asked
    return get


def agent(aid, version='1.4.0', image=IMAGE, caps=('self_update',), tags=(), connected=True, trial=False,
          lease=None, pending=None, last_seen=0, rolled_back=()):
    report = {'capabilities': list(caps),
              'agent_update': {'running': version, 'image_id': image, 'trial': trial, 'pending': pending,
                               'rolled_back': list(rolled_back)}}
    if lease is not None:
        report['lease'] = lease
    return {'id': aid, 'name': aid.upper(), 'version': version, 'connected': connected, 'tags': list(tags),
            'report': report, 'last_seen': last_seen}


# the release -----------------------------------------------------------------------------------
def test_the_newest_release_is_fetched_once_and_kept(releases):
    assert agent_updates.refresh(releases) == '1.5.0'
    assert agent_updates.latest() == meta()
    assert agent_updates.bundle_file('floorbit-agent-1.5.0.tar.gz').read_bytes() == DATA
    assert agent_updates.bundle_file('floorbit-agent-1.4.0.tar.gz') is None
    assert releases.asked[1] == ('https://github.com/bitsandbricks-ch/floorbit-agent/releases/download/'
                                 'v1.5.0/floorbit-agent-1.5.0.tar.gz')
    releases.asked.clear()
    assert agent_updates.refresh(releases) is None
    assert releases.asked == [agent_updates.RELEASE_URL]     # the same release: not downloaded again


def test_a_release_that_differs_from_its_listing_is_not_kept(releases):
    releases.data = b'something else'
    with pytest.raises(ValueError, match='differs'):
        agent_updates.refresh(releases)
    assert agent_updates.latest() is None
    releases.meta = {**meta(), 'file': '../../etc/passwd'}
    with pytest.raises(ValueError, match='no agent update'):
        agent_updates.refresh(releases)


def test_a_newer_release_replaces_the_older_file(releases):
    agent_updates.refresh(releases)
    releases.meta = meta('1.6.0')
    assert agent_updates.refresh(releases) == '1.6.0'
    names = sorted(p.name for p in agent_updates.folder().glob('*.tar.gz'))
    assert names == ['floorbit-agent-1.6.0.tar.gz']


# who gets it -----------------------------------------------------------------------------------
def test_an_agent_alone_gets_a_newer_release_built_for_its_image():
    m = meta()
    offered = {k: m[k] for k in ('version', 'file', 'sha256', 'image')}
    assert agent_updates.offer_for('a', [agent('a')], meta=m) == offered
    assert agent_updates.offer_for('a', [agent('a', version='1.5.0')], meta=m) is None
    assert agent_updates.offer_for('a', [agent('a', image='ffffffffffffffff')], meta=m) is None
    assert agent_updates.offer_for('a', [agent('a', caps=())], meta=m) is None
    assert agent_updates.offer_for('a', [agent('a')], meta=meta(protocol=3)) is None
    assert agent_updates.offer_for('nope', [agent('a')], meta=m) is None


def test_a_group_updates_one_agent_at_a_time_and_its_primary_last():
    m = meta()
    group = [agent('a', tags=['hall'], lease=True), agent('b', tags=['hall'], lease=False),
             agent('c', tags=['hall'], lease=False)]
    assert [agent_updates.offer_for(i, group, meta=m) is not None for i in 'abc'] == [False, True, False]
    # b restarts on it and is on probation: nobody else yet.
    group[1] = agent('b', version='1.5.0', tags=['hall'], trial=True)
    assert [agent_updates.offer_for(i, group, meta=m) is not None for i in 'ac'] == [False, False]
    # b kept it: c next, and the primary only when it's the last.
    group[1] = agent('b', version='1.5.0', tags=['hall'])
    assert [agent_updates.offer_for(i, group, meta=m) is not None for i in 'ac'] == [False, True]
    group[2] = agent('c', version='1.5.0', tags=['hall'])
    assert agent_updates.offer_for('a', group, meta=m) is not None


def test_a_group_waits_for_an_agent_that_just_went_away():
    m = meta()
    group = [agent('a', tags=['hall'], lease=True), agent('b', tags=['hall'], connected=False, last_seen=1000)]
    assert agent_updates.offer_for('a', group, now=1000 + 60, meta=m) is None
    # Gone for good (a broken box): the others don't wait for it forever.
    assert agent_updates.offer_for('a', group, now=1000 + agent_updates.BACK_WITHIN, meta=m) is not None


def test_agents_of_other_groups_update_side_by_side():
    m = meta()
    agents = [agent('a', tags=['hall-1']), agent('b', tags=['hall-2'])]
    assert agent_updates.offer_for('a', agents, meta=m) and agent_updates.offer_for('b', agents, meta=m)


@pytest.mark.parametrize(('row', 'state'), [
    (agent('a', version='1.5.0'), 'current'),
    (agent('a', trial=True), 'updating'),
    (agent('a'), 'installing'),
    (agent('a', caps=()), 'pull'),
    (agent('a', image='ffffffffffffffff'), 'image'),
    (agent('a', pending={'version': '1.5.0', 'why': 'waits for approval on the agent'}), 'approve'),
    (agent('a', pending={'version': '1.5.0', 'why': 'agent updates are off here (FLOORBIT_AGENT_UPDATES)'}), 'off'),
    (agent('a', pending={'version': '1.5.0', 'why': 'refused: bad signature'}), 'refused'),
    (agent('a', rolled_back=['1.5.0']), 'rolled_back'),
])
def test_the_page_says_where_each_agent_stands(row, state):
    assert agent_updates.status(row, meta())['state'] == state
    assert agent_updates.status(row, meta())['latest'] == '1.5.0'


def test_without_a_release_the_page_says_so():
    assert agent_updates.status(agent('a'), None) == {'latest': None, 'state': 'none', 'why': ''}


# what the agent says ---------------------------------------------------------------------------
def test_an_agents_update_report_keeps_only_known_shapes():
    raw = {'policy': 'rm -rf', 'running': '1.4.0', 'image': '1.4.0', 'image_id': 'not-hex', 'trial': 1,
           'keys': ['1687a3ed9b528f3b'], 'pending': {'version': '../1', 'why': 'x' * 900},
           'rolled_back': ['1.3.0', {'x': 1}], 'events': [{'at': 5, 'event': 'installed', 'version': '1.4.0'},
                                                         {'at': 6, 'event': 'pwned', 'version': '1'}]}
    clean = agent_updates.clean(raw)
    assert clean['policy'] == 'auto' and clean['image_id'] == '' and clean['trial'] is True
    assert clean['pending'] == {'version': '', 'why': 'x' * 300}
    assert clean['rolled_back'] == ['1.3.0'] and [e['event'] for e in clean['events']] == ['installed']
    assert agent_updates.clean('nope') is None


# end to end, as an agent sees it ----------------------------------------------------------------
def test_an_agent_is_offered_the_update_and_fetches_it(client, anon_client, releases, monkeypatch):
    from floorbit import agent_plugins
    monkeypatch.setattr(agent_plugins, 'reload_agents', lambda: None)
    agent_updates.refresh(releases)
    made = enrol(client, 'Hall agent')
    agent_link.tunnel.seen(agent=made['id'])
    cfg = anon_client.get('/api/agent/v1/plugins', headers=head(made['key'])).get_json()
    assert 'agent_update' not in cfg                       # no report yet: it may be an older agent
    report = {'capabilities': ['lease', 'self_update'],
              'agent_update': {'policy': 'auto', 'running': '1.4.0', 'image_id': IMAGE, 'booted': True,
                               'keys': ['1687a3ed9b528f3b'], 'trial': False}}
    assert anon_client.post('/api/agent/v1/report', json={'report': report},
                            headers=head(made['key'])).status_code == 200
    cfg = anon_client.get('/api/agent/v1/plugins', headers=head(made['key'])).get_json()
    assert cfg['agent_update']['version'] == '1.5.0'
    res = anon_client.get(f"/api/agent/v1/agent-bundles/{cfg['agent_update']['file']}", headers=head(made['key']))
    assert res.status_code == 200 and res.data == DATA
    assert anon_client.get('/api/agent/v1/agent-bundles/floorbit-agent-9.tar.gz',
                           headers=head(made['key'])).status_code == 404
    assert anon_client.get(f"/api/agent/v1/agent-bundles/{cfg['agent_update']['file']}").status_code == 401
    listed = client.get('/api/agents').get_json()
    assert listed['agent_release'] == '1.5.0'
    assert listed['agents'][0]['self_update'] == {'latest': '1.5.0', 'state': 'installing', 'why': ''}


def test_each_step_of_an_agents_update_goes_to_the_audit_log(client, anon_client, monkeypatch):
    from floorbit import agent_plugins
    monkeypatch.setattr(agent_plugins, 'reload_agents', lambda: None)
    made = enrol(client, 'Hall agent')
    agent_link.tunnel.seen(agent=made['id'])
    import time
    now = time.time()
    events = [{'at': now, 'event': 'installed', 'version': '1.5.0', 'detail': 'was 1.4.0'},
              {'at': now + 1, 'event': 'rolled back', 'version': '1.5.0', 'detail': 'did not reach Floorbit'}]
    report = {'capabilities': ['self_update'], 'agent_update': {'running': '1.4.0', 'events': events}}
    for _ in range(2):      # the same report again logs nothing new
        anon_client.post('/api/agent/v1/report', json={'report': report}, headers=head(made['key']))
    actions = [e['action'] for e in audit.read(area='agents')[0] if 'agent update' in e['action']]
    assert sorted(actions) == ['Hall agent: installed agent update 1.5.0',
                               'Hall agent: rolled back agent update 1.5.0 (did not reach Floorbit)']
