"""Where a row's seat cables plug in (floorbit/cable_lanes.py, issue #1342)."""
import pytest

from floorbit import cable_lanes, cable_plan, seat_rows


def _row(rid, gap=0, side='', **more):
    return {'id': str(rid), 'seats': 4, 'shape': 'line', 'gap': gap, 'side': side, **more}


def _by_row(block):
    out = {}
    for (r, _), v in cable_lanes.lanes(block).items():
        out.setdefault(r, set()).add(v)
    return {r: vs.pop() for r, vs in out.items() if len(vs) == 1}


# Two table pairs: rows 1 and 2 with a small cable gap, rows 3 and 4 touching, an aisle between.
PAIRS = [(1, 0), (2, 0.5), (3, 3), (4, 0)]


def test_rows_with_chairs_plug_in_behind_the_tables():
    block = {'rows': [_row(i, g, 'left' if i % 2 else 'right') for i, g in PAIRS]}
    # Row 1 sits above (left of a row running right is up): its cables run in the gap below it.
    assert _by_row(block) == {0: 1.25, 1: 1.25, 2: 6.5, 3: 6.5}


def test_chair_side_plugs_in_where_the_player_sits():
    rows = [_row(i, g, 'left' if i % 2 else 'right') for i, g in PAIRS]
    rows[0]['cables'] = 'chair'
    rows[1]['cables'] = 'behind'
    # Nothing above row 1: its lane runs half a seat out from the block.
    assert _by_row({'rows': rows})[0] == -0.5 and _by_row({'rows': rows})[1] == 1.25


def test_rows_without_chairs_take_the_gap_and_a_cable_gap_before_the_aisle():
    block = {'rows': [_row(i, g) for i, g in PAIRS]}
    assert _by_row(block) == {0: 1.25, 1: 1.25, 2: 4.0, 3: 6.5}


def test_rows_without_a_line_to_run_along_keep_the_route_along_the_block():
    lone = {'rows': [_row(1)]}
    u = {'rows': [_row(1), {'id': '2', 'seats': 8, 'shape': 'u'}]}
    free = {'rows': [_row(1), _row(2)], 'seat_at': {'1,0': [0, 0]}}
    assert cable_lanes.lanes(lone) == {} and cable_lanes.lanes(free) == {}
    assert set(_by_row(u)) == {0}


def test_a_turned_over_row_keeps_its_chairs_on_the_same_side():
    # Mirrored, the row runs right to left; its chairs (left of the way it runs) stay above.
    block = {'rows': [_row(1, side='left', mirror=True), _row(2, gap=1, side='right')]}
    assert _by_row(block) == {0: 1.5, 1: 1.5}


def test_the_row_keeps_where_its_cables_plug_in():
    assert seat_rows.clean_row(_row(1, cables='chair'))['cables'] == 'chair'
    assert 'cables' not in seat_rows.clean_row(_row(1))
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean_row(_row(1, cables='front'))


def test_a_cable_to_a_turned_block_runs_in_its_lane():
    block = {'id': 'b1', 'name': 'A', 'x': 40, 'y': 40, 'rotation': 90, 'naming': 'block',
             'rows': [_row(1, side='left'), _row(2, gap=1, side='right')]}
    data = {'seat_blocks': [block]}
    seats, boxes = cable_plan.geometry(data, 'main')
    x, y, _ = seats['A-1']
    bends = cable_plan._to_seat((10, 20), (x, y), boxes['b1'], 'A-1')
    # Turned a quarter, the rows stand upright: the lane is beside the seat, the plug comes in across.
    assert bends[-1][1] == pytest.approx(y) and bends[-1][0] != pytest.approx(x)
    assert abs(bends[-1][0] - x) == pytest.approx(1.0 * cable_plan.PITCH_X)
