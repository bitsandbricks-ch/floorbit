"""Feature switches say which kinds of device they are about (#878)."""

from types import SimpleNamespace

from floorbit import inventory_scope
from floorbit.plugins.agent import check_agent_block


def test_core_features_name_their_roles(client):
    feats = {f['id']: f for f in client.get('/api/inventory/groups').get_json()['features']}
    assert feats['ports']['roles'] == ['switch']
    assert feats['terminal']['roles'] == ['switch', 'router', 'firewall']
    assert all(feats[f]['per_device'] for f in inventory_scope.CORE_FEATURES)


def test_a_plugin_is_per_device_only_with_agent_targets():
    plain = SimpleNamespace(id='pfsense', agent=None)
    assert inventory_scope.feature_scope(plain) == (False, None)
    anywhere = SimpleNamespace(id='x', agent={'targets': {'credentials': ['ssh'], 'roles': None}})
    assert inventory_scope.feature_scope(anywhere) == (True, None)
    wifi = SimpleNamespace(id='y', agent={'targets': {'credentials': ['api'], 'roles': ['access-point']}})
    assert inventory_scope.feature_scope(wifi) == (True, ['access-point'])
    assert inventory_scope.feature_scope(SimpleNamespace(id='telemetry', agent=None))[0] is True


def test_manifest_roles_are_checked():
    ok = {'uses': ['agent'], 'agent': {'targets': {'credentials': ['ssh'], 'roles': ['switch', 'router']}}}
    assert check_agent_block(ok) == ''
    bad = {'uses': ['agent'], 'agent': {'targets': {'credentials': ['ssh'], 'roles': ['toaster']}}}
    assert 'agent.targets.roles' in check_agent_block(bad)
