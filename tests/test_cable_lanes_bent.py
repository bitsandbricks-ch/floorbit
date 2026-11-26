"""Cable routes that follow bent rows (floorbit/cable_lanes.py ``paths``, issue #1208)."""
import pytest

from floorbit import cable_lanes, cable_plan
from floorbit.blueprints import screen

U = {'id': 'b1', 'name': 'U', 'x': 40, 'y': 40, 'rotation': 0, 'naming': 'block',
     'rows': [{'id': '1', 'seats': 8, 'shape': 'u'}]}


def test_a_u_gets_a_lane_outside_with_square_corners():
    lane, i = cable_lanes.paths(U)[0, 0]
    # Chairs inside the U: the lane runs half a seat outside its seats, one past each end.
    assert lane[0] == (-0.5, -0.5) and lane[-1] == (6.5, -0.5)
    assert (-0.5, 3.5) in lane and (6.5, 3.5) in lane
    assert lane[i] == (-0.5, 0.5)


def test_cables_on_the_chair_side_run_inside():
    block = {'rows': [{'id': '1', 'seats': 8, 'shape': 'u', 'cables': 'chair'}]}
    lane, i = cable_lanes.paths(block)[0, 0]
    assert lane[i] == (1.5, 0.5)


def test_an_arc_has_a_lane_and_the_seats_point_into_it_in_order():
    block = {'rows': [{'id': '1', 'seats': 6, 'shape': 'arc', 'bend': 90}]}
    found = cable_lanes.paths(block)
    assert sorted(i for _, i in found.values()) == [1, 2, 3, 4, 5, 6]
    assert len(found[0, 0][0]) == 8


def test_rows_without_a_side_or_placed_freely_have_no_bent_lane():
    path = {'rows': [{'id': '1', 'seats': 3, 'shape': 'path', 'path': [[0, 0], [2, 2], [4, 0]]}]}
    free = {**U, 'seat_at': {'1,0': [0, 0]}}
    straight = {'rows': [{'id': '1', 'seats': 4, 'shape': 'line', 'side': 'left'},
                         {'id': '2', 'seats': 4, 'shape': 'line', 'gap': 1, 'side': 'right'}]}
    assert cable_lanes.paths(path) == {} and cable_lanes.paths(free) == {} and cable_lanes.paths(straight) == {}


def test_a_cable_follows_the_u_round_its_corner():
    seats, boxes = cable_plan.geometry({'seat_blocks': [U]}, 'main')
    x, y, _ = seats['U-4']
    route = cable_plan._tidy([(10, 20), *cable_plan._to_seat((10, 20), (x, y), boxes['b1'], 'U-4'), (x, y)])
    # Down the U's left side outside it, along the bottom, up into the seat (cableRoute.test.ts).
    assert route == [(10, 20), (33, 20), (33, 46.4), (39, 46.4), (39, 43.2)]


def test_a_cable_takes_the_nearer_end():
    seats, boxes = cable_plan.geometry({'seat_blocks': [U]}, 'main')
    x, y, _ = seats['U-8']
    bends = cable_plan._to_seat((60, 20), (x, y), boxes['b1'], 'U-8')
    assert bends[-1] == pytest.approx((47, 36.8))
    assert all(px >= 47 - 1e-6 for px, _ in bends)


def test_the_plan_sends_each_bent_lane_once_per_row():
    drawing, _ = screen.plan({'seat_blocks': [U]})
    shape = drawing['shapes'][0]
    assert list(shape['lanes']) == ['0'] and len(shape['lanes']['0']) == 12
    cell = next(c for c in shape['cells'] if c['seat'] == 'U-4')
    assert cell['li'] == 5 and 'lane' not in cell
