"""The demo's made-up local agents (issue #998): their pages work, they take no calls, and nobody
can sign in as one."""
import pytest

from floorbit import agent_link, sources
from floorbit.blueprints import demo as demo_bp


@pytest.fixture
def demo(client, app_module):
    client.put('/api/settings/plugins/demo', json={'enabled': True})
    with app_module.app.app_context():
        demo_bp._seed_agents()
    return client


def test_two_connected_agents_with_their_pages(demo):
    body = demo.get('/api/agents').get_json()
    agents = {a['name']: a for a in body['agents']}
    assert set(agents) == {'Hall agent A', 'Hall agent B'}
    a = agents['Hall agent A']
    assert a['connected'] and a['demo'] and a['address'].startswith('192.0.2.')
    assert a['report']['vrrp'] == {'primary': True, 'holds': ['192.0.2.20']}
    assert a['report']['plugins']['telemetry']['status'] == 'ok'
    history = demo.get(f"/api/agents/{a['id']}/history?hours=1").get_json()
    assert len(history['series']['points']) > 20
    devices = demo.get(f"/api/agents/{a['id']}/devices").get_json()
    assert devices['error'] is None and devices['connected']
    settings = demo.get(f"/api/agents/{a['id']}/settings")
    assert settings.status_code == 200
    renamed = demo.patch(f"/api/agents/{a['id']}", json={'name': 'Main hall agent'})
    assert renamed.status_code == 200


def test_they_take_no_calls_and_have_no_key(demo):
    # The demo plugin keeps answering: monitoring doesn't go to the made-up agents.
    assert not agent_link.active()
    assert sources.monitoring().name == 'demo'
    a = demo.get('/api/agents').get_json()['agents'][0]
    assert agent_link.check(f"{agent_link.PREFIX}{a['id']}_anything") is None
    made = demo.post(f"/api/agents/{a['id']}/rotate")
    assert made.status_code == 400 and 'no key' in made.get_json()['error']


def test_seeded_only_once_and_never_next_to_real_agents(demo, app_module):
    with app_module.app.app_context():
        demo_bp._seed_agents()
    assert len(demo.get('/api/agents').get_json()['agents']) == 2
    data = {'agents': [{'id': 'abcd0001', 'name': 'Real'}]}
    from floorbit import agent_demo
    assert agent_demo.seed(data) is False and len(data['agents']) == 1


def test_hidden_with_the_demo_off(demo):
    demo.put('/api/settings/plugins/demo', json={'enabled': False})
    assert demo.get('/api/agents').get_json()['agents'] == []
