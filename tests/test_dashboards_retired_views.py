"""Dashboards saved with a rich widget ("view" pane, retired in #1045) read as the matching tile."""
from floorbit import dashboards
from floorbit.store import load_data, save_data


def test_a_saved_view_pane_reads_as_its_tile_or_an_empty_pane(client):
    data = load_data()
    data[dashboards.KEY] = [{'id': 'old', 'name': 'Old', 'sections': [{'panels': [
        {'x': 0, 'y': 0, 'w': 6, 'h': 6, 'node': {'pane': {'kind': 'view', 'view': 'health', 'title': 'Checks',
                                                           'expanded': True}}},
        {'x': 6, 'y': 0, 'w': 6, 'h': 6, 'node': {'pane': {'kind': 'view', 'view': 'endpoints'}}},
    ]}]}]
    save_data(data)
    layout = client.get('/api/dashboards/old').get_json()
    panes = [p['node']['pane'] for p in layout['sections'][0]['panels']]
    assert panes[0] == {'kind': 'tile', 'tile': 'floorbit/w/service_health', 'title': 'Checks'}
    assert panes[1] == {'kind': 'empty'}   # IP/MAC search is a page of its own now
    # Saving it back keeps the tiles: the dashboard no longer holds a view.
    assert client.put('/api/dashboards/old', json=layout).status_code == 200
    assert {p['kind'] for p in dashboards.layout_panes(dashboards.get('old'))} == {'tile', 'empty'}


def test_every_retired_view_maps_to_a_known_tile():
    from floorbit import dashboard_core
    assert set(dashboards.RETIRED_VIEWS.values()) <= set(dashboard_core.TILES)
