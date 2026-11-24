"""A path row in pieces (Mike's row Z: a U of seats with a straight line of seats inside it)."""
import pytest

from floorbit import seat_rows

U = [[0, 6], [0, 0], [20, 0], [20, 6]]
LINE = [[4, 4], [16, 4]]


def test_seats_run_through_the_pieces_in_order():
    row = seat_rows.clean_row({'seats': 44, 'shape': 'path', 'path': U, 'pieces': [{'path': LINE, 'seats': 10}]})
    assert row['pieces'] == [{'path': [[4.0, 4.0], [16.0, 4.0]], 'seats': 10}]
    seats = seat_rows.row_seats(row)
    assert len(seats) == 44
    # Seat 35 is the first of the second piece: half a seat along the line.
    assert seats[34] == pytest.approx((4.5, 4.0, 0.0))
    assert seats[43] == pytest.approx((13.5, 4.0, 0.0))
    # The first piece starts where it always did.
    assert seats[0] == pytest.approx((0.0, 5.5, -90.0))


def test_the_first_piece_keeps_at_least_one_seat():
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean_row({'seats': 10, 'shape': 'path', 'path': U, 'pieces': [{'path': LINE, 'seats': 10}]})


@pytest.mark.parametrize('pieces', [
    [{'path': LINE, 'seats': 0}],
    [{'path': [[1, 1]], 'seats': 2}],
    ['nope'],
    [{'path': LINE, 'seats': 1}] * 8,
])
def test_bad_pieces_are_refused(pieces):
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean_row({'seats': 40, 'shape': 'path', 'path': U, 'pieces': pieces})


def test_only_a_path_keeps_pieces():
    row = seat_rows.clean_row({'seats': 12, 'shape': 'line', 'pieces': [{'path': LINE, 'seats': 2}]})
    assert 'pieces' not in row
