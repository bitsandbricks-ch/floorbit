"""An agent whose monitoring plugin isn't set up (LibreNMS on by default, no URL) is not asked for
the device list every minute: the agent source says it is off until the agent says otherwise."""
import pytest

from floorbit import agent_link


@pytest.fixture
def agent(monkeypatch):
    calls = []
    state = {'connected': {'a1'}, 'answer': False}
    monkeypatch.setattr(agent_link, '_set_up', {'at': None, 'value': True})
    monkeypatch.setattr(agent_link.tunnel, 'connected_agents', lambda now=None: state['connected'])

    def ask(method, args=()):
        calls.append(method)
        answer = state['answer']
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(agent_link, 'ask', ask)
    return state, calls


def test_an_agent_without_monitoring_turns_the_source_off(agent):
    _, calls = agent
    assert agent_link.monitoring_source().enabled() is False
    assert calls == ['configured']


def test_the_answer_is_kept_for_a_while(agent):
    state, calls = agent
    assert agent_link.monitoring_set_up(now=100) is False
    state['answer'] = True
    assert agent_link.monitoring_set_up(now=110) is False      # still the kept answer
    assert agent_link.monitoring_set_up(now=100 + agent_link.SET_UP_EVERY) is True
    assert calls == ['configured', 'configured']


def test_an_agent_away_keeps_the_last_answer(agent):
    state, calls = agent
    state['answer'] = True
    assert agent_link.monitoring_set_up(now=0) is True
    state['answer'] = agent_link.AgentUnavailable('gone')
    assert agent_link.monitoring_set_up(now=100) is True
    state['connected'] = set()
    assert agent_link.monitoring_set_up(now=200) is True
    assert calls == ['configured', 'configured']


def test_an_agent_with_no_monitoring_plugin_at_all(agent):
    state, _ = agent
    state['answer'] = agent_link.AgentError('No monitoring plugin is set up on the agent')
    assert agent_link.monitoring_set_up(now=0) is False


def test_pages_stop_asking_an_agent_without_monitoring(agent, monkeypatch):
    # Asking anyway failed every call and showed "Local agent has not answered yet" on Problems.
    from floorbit import sources
    _, calls = agent
    monkeypatch.setattr(agent_link, 'active', lambda: True)
    monkeypatch.setattr(sources, '_override', None)
    sources.mark_failed('agent', 'The local agent is not connected.', 'Local agent')   # asked before it said
    monitoring = sources.monitoring()
    assert monitoring.enabled() is False
    assert monitoring.neighbours('sw-a-01') == []
    assert calls == ['configured']
    assert not sources.offline()
