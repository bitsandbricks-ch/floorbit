"""A row turned over left to right (mirror) or upside down (flip) (floorbit/seat_rows.py)."""
import pytest

from floorbit import seat_layout, seat_rows


def places(row):
    at, w, h = seat_layout.places({'rows': [row]})
    return [at[0, c] for c in range(row['seats'])], w, h


def test_mirror_and_flip_are_kept_and_default_off():
    plain = seat_rows.clean_row({'seats': 4})
    assert plain['mirror'] is False and plain['flip'] is False
    turned = seat_rows.clean_row({'seats': 4, 'mirror': 1, 'flip': 'yes'})
    assert turned['mirror'] is True and turned['flip'] is True


def test_a_mirrored_l_turns_the_other_way_and_keeps_its_seat_order():
    l_row = seat_rows.clean_row({'seats': 4, 'shape': 'l', 'sides': [2, 2]})
    seats, w, h = places(l_row)
    mirrored, mw, mh = places({**l_row, 'mirror': True})
    assert (mw, mh) == (w, h)
    # Same seats, the other way round: the arm stands on the right, seat 1 at its top.
    assert [(w - 1 - x, y) for x, y in seats] == mirrored
    assert mirrored[0] == (2.0, 0.0)
    angles = seat_layout.angles({'rows': [{**l_row, 'mirror': True}]})
    assert [angles[0, c] for c in range(4)] == [90, 90, 180, 180]


def test_a_flipped_u_opens_downwards():
    u = seat_rows.clean_row({'seats': 8, 'shape': 'u', 'sides': [2, 4, 2]})
    seats, w, h = places(u)
    flipped, fw, fh = places({**u, 'flip': True})
    assert (fw, fh) == (w, h)
    assert [(x, h - 1 - y) for x, y in seats] == flipped
    assert flipped[2][1] == 0          # the middle side is now on top


def test_people_stay_on_the_same_side_of_the_shape():
    u = seat_rows.clean_row({'seats': 8, 'shape': 'u'})
    assert seat_rows.side_of(u) == 'left'
    assert seat_rows.side_of({**u, 'mirror': True}) == 'right'
    assert seat_rows.side_of({**u, 'flip': True}) == 'right'
    assert seat_rows.side_of({**u, 'mirror': True, 'flip': True}) == 'left'
    line = seat_rows.clean_row({'seats': 4, 'side': 'right', 'mirror': True})
    assert seat_rows.side_of(line) == 'left'
    assert seat_rows.side_of(seat_rows.clean_row({'seats': 4, 'mirror': True})) == ''


def test_mirror_and_flip_together_turn_the_row_half_round():
    arc = seat_rows.clean_row({'seats': 7, 'shape': 'arc', 'bend': 90})
    seats, w, h = places(arc)
    both, _, _ = places({**arc, 'mirror': True, 'flip': True})
    turned = [v for x, y in seats for v in (w - 1 - x, h - 1 - y)]
    assert turned == pytest.approx([v for p in both for v in p], abs=1e-3)
