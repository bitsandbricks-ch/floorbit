"""The editor's menu: a tool rail on the left and one panel on the right (search, layers, switches)."""


def test_editor_has_the_tool_rail_and_the_panel(client):
    page = client.get("/").get_data(as_text=True)
    assert 'id="tool-rail"' in page and 'id="edit-panel"' in page
    for panel in ("search", "layers", "switches"):
        assert f'class="tool-btn rail-panel-btn" type="button" data-panel="{panel}"' in page
        assert f'data-page="{panel}"' in page
    # The tools and the inputs the other editor scripts look up by id are still there, once.
    for el in ("tool-select", "tool-add-switch", "tool-add-block", "tool-draw", "btn-undo", "btn-redo",
               "btn-snap", "btn-shortcuts", "universal-search", "switch-search", "switch-list", "sync-section"):
        assert page.count(f'id="{el}"') == 1, el
    # The old left sidebar and floating toolbar are gone.
    assert 'id="sidebar"' not in page and 'class="toolbar"' not in page
    order = [page.index(f"/static/js/editor/{name}.js") for name in ("touch", "panels", "main")]
    assert order == sorted(order)
