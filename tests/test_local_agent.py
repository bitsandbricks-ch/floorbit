"""The agent next to a self-hosted Floorbit enrols itself through a shared key file
(agent_link.bootstrap_local, docs/agent.md "The agent next to a self-hosted Floorbit")."""
import os
import stat

from floorbit import agent_link
from tests.test_agent import clean_tunnel, head  # noqa: F401  # the fixture resets the tunnel


def test_the_app_writes_the_key_and_enrols_the_local_agent(client, tmp_path, monkeypatch):
    path = tmp_path / "key" / "local-agent.key"
    monkeypatch.setenv("FLOORBIT_LOCAL_AGENT_KEY_FILE", str(path))
    assert agent_link.bootstrap_local() == agent_link.LOCAL_ID
    key = path.read_text().strip()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert agent_link.check(key)["name"] == "Local agent"
    # The agent takes its calls with it.
    assert client.get("/api/agent/v1/calls?wait=0", headers=head(key)).status_code == 200
    # A restart keeps the same key and the same single agent.
    assert agent_link.bootstrap_local() == agent_link.LOCAL_ID
    assert path.read_text().strip() == key
    agents = agent_link.all_agents()
    assert len(agents) == 1 and agents[0]["local"] is True


def test_a_new_file_replaces_the_old_key(client, tmp_path, monkeypatch):
    path = tmp_path / "local-agent.key"
    monkeypatch.setenv("FLOORBIT_LOCAL_AGENT_KEY_FILE", str(path))
    agent_link.bootstrap_local()
    old = path.read_text().strip()
    path.unlink()                         # a new pod: its memory volume starts empty
    agent_link.bootstrap_local()
    new = path.read_text().strip()
    assert new != old and agent_link.check(new) and agent_link.check(old) is None
    assert len(agent_link.all_agents()) == 1


def test_renewing_the_local_key_writes_the_file(client, tmp_path, monkeypatch):
    path = tmp_path / "local-agent.key"
    monkeypatch.setenv("FLOORBIT_LOCAL_AGENT_KEY_FILE", str(path))
    agent_link.bootstrap_local()
    old = path.read_text().strip()
    _name, key = agent_link.rotate(agent_link.LOCAL_ID)
    assert path.read_text().strip() == key
    assert agent_link.check(old)            # until the agent restarts with the new one


def test_not_without_the_file_setting_nor_in_the_agent(client, tmp_path, monkeypatch):
    path = tmp_path / "local-agent.key"
    assert agent_link.bootstrap_local() is None
    monkeypatch.setenv("FLOORBIT_LOCAL_AGENT_KEY_FILE", str(path))
    monkeypatch.setenv("FLOORBIT_AGENT_KEY", "fba_00000000_" + "x" * 30)
    assert agent_link.bootstrap_local() is None
    assert not path.exists() and agent_link.all_agents() == []
