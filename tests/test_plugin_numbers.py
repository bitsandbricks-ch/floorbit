"""Numbers a plugin.yaml or a Marketplace index gives are checked, never handed to int() as they are:
one bad value must refuse that plugin, not stop Floorbit loading the others or the Marketplace."""
import pytest
from test_plugins import turn_on, write_plugin

from floorbit import marketplace
from floorbit.plugins import REFRESH_MAX, _load, clean_touches, validate

BASE = {'id': 'demo-x', 'name': 'X', 'version': '1.0.0'}
KINDS = [('widgets', {}), ('panels', {'for': 'seat'}), ('layers', {})]
BAD = ['fast', [1], '30', 1.5, float('inf'), float('nan'), True, {'s': 1}]


@pytest.mark.parametrize('kind, extra', KINDS)
@pytest.mark.parametrize('refresh', BAD)
def test_a_refresh_that_is_no_whole_number_is_refused(kind, extra, refresh):
    err = validate({**BASE, 'uses': [kind], kind: [{'id': 'x', 'refresh': refresh, **extra}]})
    assert f'{kind}.x: refresh is a whole number of seconds' in err


@pytest.mark.parametrize('kind, extra', KINDS)
@pytest.mark.parametrize('refresh, kept', [(None, 60), (-5, 10), (5, 10), (45, 45), (10 ** 400, REFRESH_MAX)])
def test_a_refresh_is_kept_between_10_s_and_a_day(kind, extra, refresh, kept):
    item = {'id': 'x', **extra, **({} if refresh is None else {'refresh': refresh})}
    assert validate({**BASE, 'uses': [kind], kind: [item]}) == ''
    assert item['refresh'] == kept


def test_a_bad_refresh_in_plugin_yaml_is_the_plugins_error(tmp_path, app_module):
    registry = app_module.app.extensions['floorbit_plugins']
    yaml = 'id: tick\nname: Tick\nversion: "1.0"\nuses: [widgets]\nwidgets:\n  - {id: a, refresh: fast}\n'
    spec = _load(write_plugin(tmp_path, 'tick', yaml, 'from floorbit.plugins.base import Plugin\n'),
                 'development', registry.version)
    assert 'refresh is a whole number' in spec.error


@pytest.mark.parametrize('secrets, shown', [('²', 0), ('1' * 5000, 0), (10 ** 9, 99), (-1, 0), (True, 0), (3, 3)])
def test_odd_counts_in_an_index_are_cut_not_a_crash(secrets, shown):
    assert clean_touches({'secrets': secrets})['secrets'] == shown


@pytest.mark.parametrize('api, kept', [(None, 1), (2, 2), ('x', 1000), ([2], 1000), (True, 1000), (0, 1000),
                                       (10 ** 400, 1000)])
def test_an_odd_agent_api_in_an_index_never_reaches_an_old_agent(api, kept):
    entry = {'versions': [{'version': '1.0.0', 'file': 'x-1.0.0.zip', 'agent_api': api},
                          {'version': '0.9.0', 'file': 'x-0.9.0.zip'}]}
    got = marketplace.versions_of(entry)
    assert [v['version'] for v in got] == ['1.0.0', '0.9.0'] and got[0]['agent_api'] == kept


GOOD = {**BASE, 'uses': ['settings', 'actions', 'widgets', 'endpoints', 'panels', 'layers', 'pages'],
        'settings': [{'key': 'k', 'label': 'K'}], 'actions': [{'id': 'a'}], 'widgets': [{'id': 'w'}],
        'endpoints': [{'id': 'e'}], 'panels': [{'id': 'p', 'for': 'seat'}], 'layers': [{'id': 'l'}],
        'pages': [{'id': 'g', 'widgets': ['w']}]}
ODD = [True, 1.5, float('nan'), 10 ** 400, [1], [{}], [[1]], {'a': 1}, [None]]


def _with(path, value):
    import copy
    m = copy.deepcopy(GOOD)
    if len(path) == 1:
        m[path[0]] = value
    else:
        m[path[0]][0][path[1]] = value
    return m


@pytest.mark.parametrize('path', [('uses',), ('settings',), ('actions',), ('widgets',), ('pages',),
                                  ('widgets', 'id'), ('widgets', 'permission'), ('widgets', 'role'),
                                  ('widgets', 'label'), ('panels', 'id'), ('layers', 'permission'),
                                  ('pages', 'widgets'), ('pages', 'actions'), ('settings', 'type'),
                                  ('settings', 'key'), ('actions', 'params')])
@pytest.mark.parametrize('value', ODD)
def test_a_value_of_the_wrong_type_is_an_error_not_an_exception(path, value):
    assert validate(GOOD) == ''
    err = validate(_with(path, value))
    assert isinstance(err, str) and err and 'wrong type' not in err, err


def test_an_empty_label_takes_the_id():
    m = _with(('widgets', 'label'), None)
    assert validate(m) == '' and m['widgets'][0]['label'] == 'W'


@pytest.mark.parametrize('listed', [5, True, 'abc', {'a': 1}, None, [{'version': ['1'], 'file': 'x'}],
                                    [{'version': '1.0.0', 'file': ['x']}], [{'version': 1.0, 'file': 'x'}]])
def test_an_odd_versions_list_in_an_index_offers_nothing(listed):
    assert marketplace.versions_of({'versions': listed}) == []


ODD_LISTS = [True, 1, 1.5, 'x', {'a': 1}, float('nan')]


@pytest.mark.parametrize('value', ODD_LISTS)
@pytest.mark.parametrize('kind,key', [('status', 'items'), ('list', 'items'), ('table', 'columns'),
                                      ('table', 'rows'), ('sparkline', 'points')])
def test_a_widget_list_that_is_no_list_is_the_plugins_error(kind, key, value):
    from floorbit.plugins.widgets import WidgetError, check_widget
    raw = {'type': kind, 'columns': [{'key': 'a'}], key: value}
    with pytest.raises(WidgetError):
        check_widget(raw, {'id': 't'})


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_numbers_that_are_not_json_never_reach_the_browser(value):
    from floorbit.plugins.widgets import WidgetError, check_widget
    with pytest.raises(WidgetError):
        check_widget({'type': 'sparkline', 'points': [1, value]}, {'id': 't'})
    with pytest.raises(WidgetError):
        check_widget({'type': 'sparkline', 'points': [1], 'max': value}, {'id': 't'})
    stat = check_widget({'type': 'stat', 'value': value}, {'id': 't'})
    assert isinstance(stat['value'], str)


@pytest.mark.parametrize('value', ODD_LISTS)
def test_a_layer_legend_or_seats_of_the_wrong_kind_is_the_plugins_error(value):
    from floorbit.plugins import check_layer
    from floorbit.plugins.widgets import WidgetError
    for raw in ({'legend': value}, {'seats': value}):
        with pytest.raises(WidgetError):
            check_layer(raw)


ODD_YAML = """
id: oddjson
name: Odd JSON
version: "1.0"
uses: [endpoints, actions]
actions:
  - id: odd
    role: editor
    params: [{key: times, type: int}]
endpoints:
  - {id: nan}
  - {id: keys}
  - {id: fine}
"""

ODD_PY = """
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    def endpoint_nan(self, args):
        return {'ping': float('nan')}

    def endpoint_keys(self, args):
        return {(1, 2): 'tuple key'}

    def run_odd(self, params):
        return {'message': 'ran', 'ping': float('inf'), 'times': params['times']}

    def endpoint_fine(self, args):
        return [1, 'two', {'three': 3.5}]
"""


@pytest.fixture
def oddjson(tmp_path, app_module):
    registry = app_module.app.extensions['floorbit_plugins']
    spec = _load(write_plugin(tmp_path, 'oddjson', ODD_YAML, ODD_PY), 'development', registry.version)
    assert spec.error == ''
    registry.specs[spec.id] = spec
    registry._register_settings()
    yield registry
    registry.specs.pop(spec.id, None)


def test_an_endpoint_answer_no_browser_can_read_is_a_502(client, oddjson):
    turn_on(client, 'oddjson')
    for endpoint in ('nan', 'keys'):
        resp = client.get(f'/api/plugins/oddjson/endpoints/{endpoint}')
        assert resp.status_code == 502, endpoint
        assert 'not JSON' in resp.get_json()['error']
    assert any('not JSON' in line for line in str(oddjson.logs.get('oddjson')).splitlines())
    resp = client.get('/api/plugins/oddjson/endpoints/fine')
    assert resp.status_code == 200 and resp.get_json() == [1, 'two', {'three': 3.5}]


@pytest.mark.parametrize('body', ['[1, 2]', '"times"', '7'])
def test_an_action_body_that_is_no_object_is_refused(client, oddjson, body):
    turn_on(client, 'oddjson')
    resp = client.post('/api/plugins/oddjson/actions/odd', data=body, content_type='application/json')
    assert resp.status_code == 400 and 'JSON object' in resp.get_json()['error']


@pytest.mark.parametrize('times', [float('inf'), float('-inf'), float('nan')])
def test_an_infinite_whole_number_is_refused(times):
    # floorbit/json_body.py refuses these in a request; the check behind it holds on its own too.
    from floorbit.blueprints.plugins import _params
    from floorbit.plugins import PluginError
    with pytest.raises(PluginError, match='whole number'):
        _params({'params': [{'key': 'times', 'type': 'int'}]}, {'times': times})


def test_action_data_no_browser_can_read_is_left_out(client, oddjson):
    turn_on(client, 'oddjson')
    resp = client.post('/api/plugins/oddjson/actions/odd', json={'times': 2})
    assert resp.status_code == 200
    assert resp.get_json() == {'ok': True, 'message': 'ran', 'data': {}}
    assert 'not JSON' in str(oddjson.logs.get('oddjson'))


@pytest.mark.parametrize('pattern, value', [
    ('floorbit.plugins.ID_RE', 'lancache\n'), ('floorbit.plugins.NAME_RE', 'ping\n'),
    ('floorbit.plugins.documents.COLLECTION_RE', 'notes\n'), ('floorbit.marketplace.VERSION_RE', '1.0.0\n'),
    ('floorbit.agent_plugins.PLUGIN_ID_RE', 'lancache\n'), ('floorbit.plugins.bundles.ID_RE', 'lancache\n'),
])
def test_a_trailing_newline_is_no_valid_name(pattern, value):
    # "$" matches before a final newline; names become paths and store keys.
    import importlib
    module, name = pattern.rsplit('.', 1)
    regex = getattr(importlib.import_module(module), name)
    assert regex.match(value) is None and regex.match(value.strip())


@pytest.mark.parametrize('value', [float('inf'), float('-inf'), float('nan')])
def test_an_infinite_whole_number_setting_is_refused(value):
    from floorbit import settings
    with pytest.raises(settings.SettingsError, match='whole number'):
        settings._coerce({'type': 'int', 'label': 'Cache'}, value)


def test_a_read_that_overlapped_a_change_is_not_kept(app_module, monkeypatch):
    # The read began before "turn it on" was saved and finished after: caching it hid the change
    # for STATE_TTL ("No port actions plugin is on" right after an admin turned it on).
    from floorbit import store
    registry = app_module.app.extensions['floorbit_plugins']
    registry._cache = None
    real = store.read_json

    def slow_read(path, default=None):
        old = real(path, default)
        monkeypatch.setattr(store, 'read_json', real)
        registry._update('sample-x', enabled=True)   # lands while this read is on its way
        return old

    monkeypatch.setattr(store, 'read_json', slow_read)
    assert 'sample-x' not in registry._all()
    assert registry._record('sample-x') == {'enabled': True}
