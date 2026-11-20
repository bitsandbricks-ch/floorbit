"""The enrol card's docker run line names the agent image this Floorbit is tested with (issue #1166)."""
from floorbit import agent_link


def test_the_image_is_pinned_to_agent_ref():
    with open(agent_link._AGENT_REF) as f:
        ref = f.read().strip()
    assert agent_link.agent_image() == f'ghcr.io/bitsandbricks-ch/floorbit-agent:{ref[:12]}'


def test_without_agent_ref_it_falls_back_to_latest(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_link, '_AGENT_REF', str(tmp_path / 'missing'))
    assert agent_link.agent_image().endswith(':latest')
    (tmp_path / 'bad').write_text('main\n')
    monkeypatch.setattr(agent_link, '_AGENT_REF', str(tmp_path / 'bad'))
    assert agent_link.agent_image().endswith(':latest')


def test_enrol_and_a_new_key_hand_out_the_image(client):
    made = client.post('/api/agents', json={'name': 'Hall B'}).get_json()
    assert made['image'] == agent_link.agent_image()
    rotated = client.post(f"/api/agents/{made['id']}/rotate").get_json()
    assert rotated['image'] == agent_link.agent_image() and rotated['key'] != made['key']
