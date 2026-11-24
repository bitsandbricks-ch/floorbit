"""A seat block is a list of rows, each with its own seats, shape and space above it (floorbit/seat_rows.py)."""
import itertools

import pytest

from floorbit import seat_layout, seat_names, seat_rows, upgrades
from floorbit.blueprints.screen import CELL


def row(rid, seats, **more):
    return {'id': rid, 'seats': seats, **more}


def test_the_grid_shape_becomes_rows_with_ids_in_their_old_order():
    block = {'id': 'b', 'cols': 4, 'rows': 3, 'row_gaps': [{'after': 1, 'size': 2}],
             'col_gaps': [{'after': 2, 'size': 1}], 'seat_at': {'0,1': [5, 5], '2,3': [1, 1]}}
    seat_rows.from_grid(block)
    assert [r['id'] for r in block['rows']] == ['1', '2', '3']
    assert [r['seats'] for r in block['rows']] == [4, 4, 4]
    assert [r['gap'] for r in block['rows']] == [0, 2.0, 0]
    assert block['rows'][2]['col_gaps'] == [{'after': 2, 'size': 1.0}]
    assert block['seat_at'] == {'1,1': [5, 5], '3,3': [1, 1]}
    assert not {'cols', 'col_gaps', 'row_gaps'} & set(block)
    # Once in rows, it is left alone.
    assert seat_rows.from_grid(block) is block and block['rows'][0]['id'] == '1'


def test_the_upgrade_moves_every_block_and_old_row_ids_still_name_the_same_rows():
    data = {'seat_blocks': [{'id': 'b', 'cols': 8, 'rows': 2, 'naming': 'rows', 'row_start': 'C'}]}
    before = seat_names.row_id(data['seat_blocks'][0], 2)
    upgrades.apply(data)
    block = data['seat_blocks'][0]
    assert isinstance(block['rows'], list) and seat_names.row_id(block, 2) == before == 'b:2'
    assert [r['name'] for r in seat_names.hall_rows(data)] == ['C', 'D']


def test_rows_of_different_lengths_line_up_and_number_on_their_own():
    block = {'id': 'b', 'naming': 'rows', 'row_start': 'E',
             'rows': seat_rows.clean([row('1', 6), row('2', 4, align='middle', gap=2), row('3', 2, align='end')])}
    assert seat_names.block_rows(block) == [[f'E-{n}' for n in range(1, 7)], [f'F-{n}' for n in range(1, 5)],
                                            ['G-1', 'G-2']]
    at, width, height = seat_layout.places(block)
    assert (width, height) == (6, 5)
    assert at[1, 0] == (1, 3) and at[2, 0] == (4, 4)    # F centred under E after a 2-seat aisle; G at the end


def test_a_running_number_runs_over_rows_of_any_length():
    block = {'name': 'A', 'rows': seat_rows.clean([row('1', 3), row('2', 2)])}
    assert seat_names.block_rows(block) == [['A-1', 'A-2', 'A-3'], ['A-4', 'A-5']]
    upside_down = {**block, 'rotation': 180}
    assert seat_names.block_rows(upside_down) == [['A-5', 'A-4', 'A-3'], ['A-2', 'A-1']]
    one_turned = {**block, 'rows': seat_rows.clean([row('1', 3, reverse=True), row('2', 2)])}
    assert seat_names.block_rows(one_turned)[0] == ['A-3', 'A-2', 'A-1']


def test_a_u_wraps_round_a_table_with_people_inside():
    u = seat_rows.clean_row({'seats': 12, 'shape': 'u'})
    assert u['sides'] == [3, 6, 3] and seat_rows.side_of(u) == 'left'
    seats = seat_rows.row_seats(u)
    # Down the left side, along the bottom, up the right side.
    assert [round(a) for _, _, a in seats] == [90] * 3 + [0] * 6 + [-90] * 3
    assert seats[0][:2] == (0.5, 0.5) and seats[3][:2] == (1.5, 3.5) and seats[-1][:2] == (7.5, 0.5)
    _, width, height = seat_layout.places({'rows': [u]})
    assert (width, height) == (8, 4)
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean_row({'seats': 12, 'shape': 'u', 'sides': [3, 3, 3]})


def test_an_arc_keeps_its_seats_a_seat_apart_and_bends_both_ways():
    arc = seat_rows.clean_row({'seats': 9, 'shape': 'arc', 'bend': 90})
    seats = seat_rows.row_seats(arc)
    steps = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in itertools.pairwise(seats)]
    assert all(0.97 < s <= 1.0 for s in steps)
    assert seats[0][2] == pytest.approx(-40) and seats[-1][2] == pytest.approx(40)
    assert seats[4][1] < seats[0][1]          # bending right, the middle is higher than the ends
    other = seat_rows.row_seats({**arc, 'bend': -90})
    assert other[4][1] > other[0][1]


def test_a_path_row_follows_its_points():
    path = seat_rows.clean_row({'seats': 4, 'shape': 'path', 'path': [[0, 0], [2, 0], [2, 3]]})
    seats = seat_rows.row_seats(path)
    got = [(round(x, 2), round(y, 2), round(a)) for x, y, a in seats]
    assert got == [(0.5, 0, 0), (1.5, 0, 0), (2, 0.5, 90), (2, 1.5, 90)]


def test_rows_are_checked():
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean([])
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean([row('1', 0)])
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean([row('1', 4, shape='circle')])
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean([row('1', 4, gap=float('nan'))])
    # A repeated or missing id gets a new one.
    rows = seat_rows.clean([row('1', 4), row('1', 4), {'seats': 2}])
    assert [r['id'] for r in rows] == ['1', '2', '3']


def test_a_block_is_made_saved_and_drawn_with_its_rows(client):
    made = client.post('/api/seat-blocks', json={'x': 50, 'y': 50, 'cols': 4, 'rows': 2, 'naming': 'rows',
                                                 'row_start': 'K'})
    assert made.status_code == 201, made.get_json()
    block = made.get_json()
    assert [r['seats'] for r in block['rows']] == [4, 4]
    rows = block['rows'] + [{'seats': 6, 'shape': 'u', 'gap': 1}]
    saved = client.put(f"/api/seat-blocks/{block['id']}", json={'rows': rows})
    assert saved.status_code == 200, saved.get_json()
    assert saved.get_json()['seat_rows'][2] == [f'M-{n}' for n in range(1, 7)]
    plan = client.get('/api/plan?hall=main').get_json()['drawing']
    shape = next(s for s in plan['shapes'] if s['id'] == block['id'])
    u = [c for c in shape['cells'] if c['rc'][0] == 2]
    assert {c.get('side') for c in u} == {'left'} and u[0]['a'] == 90
    assert shape['row_list'][2] == {'id': f"{block['id']}:3", 'row': '3', 'name': 'M'}
    assert not any('a' in c or 'side' in c for c in shape['cells'] if c['rc'][0] < 2)
    letters = [r for r in shape['rows'] if r['text'] == 'K']
    assert letters and letters[0]['x'] == pytest.approx(shape['cells'][0]['x'] - CELL / 2)
    bad = client.put(f"/api/seat-blocks/{block['id']}", json={'rows': []})
    assert bad.status_code == 400


def test_seats_placed_by_hand_follow_their_row_when_rows_move(client):
    block = client.post('/api/seat-blocks', json={'x': 50, 'y': 50, 'cols': 2, 'rows': 2, 'name': 'Q'}).get_json()
    moved = client.put(f"/api/seat-blocks/{block['id']}", json={'seat_at': {'2,1': [5, 0]}}).get_json()
    assert moved['seat_at']['2,1'][0] > moved['seat_at']['2,0'][0] + 1
    flipped = client.put(f"/api/seat-blocks/{block['id']}", json={'rows': list(reversed(moved['rows']))}).get_json()
    assert flipped['seat_at']['2,1'] == moved['seat_at']['2,1']


def test_a_circuit_keeps_its_row_when_rows_are_reordered(client):
    block = client.post('/api/seat-blocks', json={'x': 50, 'y': 50, 'cols': 2, 'rows': 2, 'naming': 'rows',
                                                  'row_start': 'P'}).get_json()
    board = client.post('/api/power/boards', json={'name': 'DB-1'}).get_json()
    feeds = [{'block': block['id'], 'rows': [2]}]
    made = client.post('/api/power/circuits', json={'name': 'Q row', 'board': board['id'], 'blocks': feeds})
    assert made.status_code in (200, 201), made.get_json()
    client.put(f"/api/seat-blocks/{block['id']}", json={'rows': list(reversed(block['rows']))})
    circuit = next(c for c in client.get('/api/power').get_json()['circuits'] if c['name'] == 'Q row')
    # Row 2 was Q; reordered it is the top row and is now lettered P, but still the same seats' row.
    assert circuit['blocks'][0]['rows'] == [2] and sorted(circuit['fed']['seats']) == ['P-1', 'P-2']


def test_a_template_from_before_rows_is_read_as_its_grid():
    from floorbit import layout_templates
    old = {'halls': [{'id': 'main', 'name': 'Hall'}],
           'seat_blocks': [{'name': 'A', 'x': 10, 'y': 10, 'cols': 3, 'rows': 2, 'row_gaps': [{'after': 1, 'size': 2}],
                            'seat_at': {'1,2': [4, 0]}, 'hall_id': 'main'}]}
    layout, dropped = layout_templates.clean_layout(old)
    block = layout['seat_blocks'][0]
    assert [(r['id'], r['seats'], r['gap']) for r in block['rows']] == [('1', 3, 0), ('2', 3, 2.0)]
    assert block['seat_at'] == {'2,2': [4.0, 0.0]} and dropped == []
