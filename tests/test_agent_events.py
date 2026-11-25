"""One agent's recent events on its page (issue #905): what the audit log holds about it, and only it."""
from test_agent import clean_tunnel, enrol  # noqa: F401  # clean_tunnel is autouse there

from floorbit import audit


def test_an_agents_page_lists_what_happened_to_it_newest_first(client):
    hall = enrol(client, 'Hall agent')
    other = enrol(client, 'Stage agent')
    assert client.post(f"/api/agents/{hall['id']}/roll").status_code == 200
    audit.record('agents', 'Hall agent: kept plugin lancache 1.2.0', user='agent', target='lancache')
    audit.record('agents', 'Hall agent: rolled back agent update 1.5.0 (did not reach Floorbit)', user='agent',
                 target=hall['id'], ok=False)
    audit.record('agents', 'Stage agent: kept plugin lancache 1.2.0', user='agent', target='lancache')
    audit.record('inventory', 'Changed device', target='Hall agent')     # another area: not about the agent
    events = client.get(f"/api/agents/{hall['id']}/events").get_json()['events']
    actions = [e['action'] for e in events]
    assert actions == ['Hall agent: rolled back agent update 1.5.0 (did not reach Floorbit)',
                       'Hall agent: kept plugin lancache 1.2.0',
                       'Asked a local agent to fetch a new key',
                       'Enrolled a local agent']
    assert events[0]['ok'] is False and events[1]['ok'] is True and events[0]['at'] > 0
    assert [e['action'] for e in client.get(f"/api/agents/{other['id']}/events").get_json()['events']] == [
        'Stage agent: kept plugin lancache 1.2.0', 'Enrolled a local agent']
    assert len(client.get(f"/api/agents/{hall['id']}/events?limit=1").get_json()['events']) == 1


def test_the_events_come_in_the_pages_language(client):
    hall = enrol(client, 'Hall agent')
    events = client.get(f"/api/agents/{hall['id']}/events", headers={'Accept-Language': 'de-CH'}).get_json()['events']
    assert events[0]['action'] != 'Enrolled a local agent'


def test_an_unknown_agent_has_no_events(client):
    assert client.get('/api/agents/nope/events').status_code == 404


def test_only_admins_see_an_agents_events(client, anon_client):
    hall = enrol(client, 'Hall agent')
    assert anon_client.get(f"/api/agents/{hall['id']}/events").status_code in (401, 403)
