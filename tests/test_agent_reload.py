"""Telling the agents to reload never holds up the save that asked for it."""
import threading
import time

from floorbit import agent_link, agent_plugins


class SlowTunnel:
    def __init__(self, agents):
        self.agents, self.calls, self.lock = agents, [], threading.Lock()
        self.release = threading.Event()

    def connected_agents(self):
        return set(self.agents)

    def call(self, method, args, timeout, targets):
        with self.lock:
            self.calls.append((method, tuple(targets)))
        self.release.wait(timeout)
        raise agent_link.AgentUnavailable('away')


def _wait_idle():
    for _ in range(200):
        if not agent_plugins._reload_running:
            return
        time.sleep(0.01)
    raise AssertionError('the reload never finished')


def test_reload_returns_at_once_and_asks_every_agent_in_parallel(monkeypatch):
    tunnel = SlowTunnel(['a1', 'a2', 'a3'])
    monkeypatch.setattr(agent_link, 'tunnel', tunnel)
    start = time.monotonic()
    agent_plugins.reload_agents()
    assert time.monotonic() - start < 0.5
    for _ in range(200):
        if len(tunnel.calls) == 3:
            break
        time.sleep(0.01)
    assert sorted(tunnel.calls) == [('plugins_reload', ('a1',)), ('plugins_reload', ('a2',)),
                                    ('plugins_reload', ('a3',))]
    tunnel.release.set()
    _wait_idle()


def test_saves_during_a_reload_fold_into_one_more_round(monkeypatch):
    tunnel = SlowTunnel(['a1'])
    monkeypatch.setattr(agent_link, 'tunnel', tunnel)
    agent_plugins.reload_agents()
    for _ in range(200):
        if tunnel.calls:
            break
        time.sleep(0.01)
    for _ in range(10):
        agent_plugins.reload_agents()
    tunnel.release.set()
    _wait_idle()
    assert len(tunnel.calls) == 2


def test_no_agents_no_thread_left_running(monkeypatch):
    monkeypatch.setattr(agent_link, 'tunnel', SlowTunnel([]))
    agent_plugins.reload_agents()
    _wait_idle()
