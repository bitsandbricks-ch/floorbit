"""Stored data from an older Floorbit moves to its current shape once (floorbit/upgrades.py), so
readers know one shape only."""
from floorbit import inventory, store, upgrades


def test_old_layout_moves_over_once_keeping_ids_and_positions():
    data = {'switches': [{'id': 'm1', 'name': 'sw-hand-01', 'x': 1, 'y': 2, 'placed': True}],
            'cached_devices': [{'id': '7', 'name': 'sw-nb-07', 'netbox_status': 'active'},
                               {'id': '8', 'name': 'sw-nb-08'}],
            'positions': {'7': {'x': 30, 'y': 40}}}
    assert upgrades.apply(data) is True
    assert not {'switches', 'cached_devices', 'positions'} & set(data)
    by_id = {d['id']: d for d in inventory.devices(data)}
    assert by_id['m1']['origin'] == 'manual' and (by_id['m1']['x'], by_id['m1']['y']) == (1, 2)
    assert by_id['7']['refs'] == {'netbox': '7'} and by_id['7']['status'] == 'active'
    assert (by_id['7']['x'], by_id['7']['y']) == (30, 40)
    assert by_id['8']['x'] is None
    assert upgrades.apply(data) is False and data[upgrades.KEY] == upgrades.CURRENT


def test_the_first_display_settings_become_settings():
    data = {'default_settings': {'hide_labels': 1, 'exclude_heatmap': True},
            'app_settings': {'display.exclude_heatmap': False}}       # saved since: wins
    upgrades.apply(data)
    assert 'default_settings' not in data
    assert data['app_settings'] == {'display.hide_labels': True, 'display.exclude_heatmap': False}


def test_accounts_from_before_roles_are_admins_and_editors_are_leads():
    data = {'auth_users': {'old': {'username': 'old'},
                           'ed': {'username': 'ed', 'role': 'editor', 'teams': {'t1': 'editor', 't2': 'viewer'}}},
            'api_tokens': {'x': {'id': 'x', 'name': 'ci'}},
            'auth_oidc': {'idp': {'role_mapping': [{'value': 'crew', 'role': 'editor'}]}}}
    upgrades.apply(data)
    assert data['auth_users']['old']['role'] == 'admin'
    assert data['auth_users']['ed'] == {'username': 'ed', 'role': 'lead', 'teams': {'t1': 'lead', 't2': 'viewer'}}
    assert data['api_tokens']['x']['role'] == 'admin'
    assert data['auth_oidc']['idp']['role_mapping'] == [{'value': 'crew', 'role': 'lead'}]


def test_block_groups_become_plan_groups_per_hall():
    data = {'halls': [{'id': 'main', 'name': 'Main'}, {'id': 'side', 'name': 'Side'}],
            'seat_blocks': [{'id': 'a', 'group': 'g'}, {'id': 'b', 'group': 'g'},
                            {'id': 'c', 'group': 'g', 'hall_id': 'side'},           # alone in its hall
                            {'id': 'd', 'group': 'h'}, {'id': 'e', 'group': 'h'}],
            'plan_groups': [{'id': 'p', 'hall_id': 'main', 'name': 'P',
                             'members': [{'kind': 'block', 'id': 'e'}, {'kind': 'mark', 'id': 'm'}]}]}
    upgrades.apply(data)
    assert all('group' not in b for b in data['seat_blocks'])
    made = [g for g in data['plan_groups'] if g['id'] != 'p']
    # g: a and b in main; c alone in side makes no group; h: e is in plan group p already, d alone.
    assert [(g['hall_id'], g['name'], [m['id'] for m in g['members']]) for g in made] == [('main', 'g', ['a', 'b'])]


def test_dashboards_saved_as_one_tree_become_a_grid():
    data = {'dashboards': [{'id': 'old', 'name': 'Old', 'root': {'pane': {'kind': 'empty'}}}]}
    upgrades.apply(data)
    old = data['dashboards'][0]
    assert 'root' not in old and old['fit'] is True
    assert old['sections'][0]['panels'][0]['node'] == {'pane': {'kind': 'empty'}}


def test_steps_are_safe_to_run_twice():
    data = {'auth_users': {'ed': {'username': 'ed', 'role': 'editor'}},
            'seat_blocks': [{'id': 'a', 'group': 'g'}, {'id': 'b', 'group': 'g'}]}
    upgrades.apply(data)
    once = repr(data)
    data[upgrades.KEY] = 0          # a later event's document runs them over the tenant's parts again
    upgrades.apply(data)
    assert repr(data) == once


def test_floorbit_moves_the_stored_file_when_it_starts(app_module):
    store.write_json(store.DATA_FILE, {'setup': {'done': True, 'steps': {}},
                                       'auth_users': {'old': {'username': 'old', 'password': 'x'}},
                                       'switches': [{'id': 's1', 'name': 'sw-01', 'x': 1, 'y': 1}]})
    said = []
    upgrades.run_at_start(log=said.append)
    stored = store.read_json(store.DATA_FILE)
    assert stored[upgrades.KEY] == upgrades.CURRENT and 'switches' not in stored
    assert stored['auth_users']['old']['role'] == 'admin' and stored['inventory'][0]['name'] == 'sw-01'
    assert said
    upgrades.run_at_start(log=said.append)     # nothing left to move: not saved again, nothing said
    assert len(said) == 1


def test_an_older_backup_restores_in_the_current_shape(client):
    from floorbit.blueprints import backup
    old = backup.make_backup(store.load_data())
    old['layout'].pop('inventory', None)
    old['layout']['switches'] = [{'id': 's1', 'name': 'sw-old-01', 'x': 2, 'y': 3}]
    old['layout']['seat_blocks'] = [{'id': 'a', 'name': 'A', 'x': 1, 'y': 1, 'cols': 2, 'rows': 1, 'group': 'g'},
                                    {'id': 'b', 'name': 'B', 'x': 5, 'y': 1, 'cols': 2, 'rows': 1, 'group': 'g'}]
    r = client.post('/api/settings/backup', json=old)
    assert r.status_code == 200, r.get_json()
    data = store.load_data()
    assert [d['name'] for d in inventory.devices(data)] == ['sw-old-01']
    assert all('group' not in b for b in data['seat_blocks'])
    assert [sorted(m['id'] for m in g['members']) for g in data.get('plan_groups') or []] == [['a', 'b']]
