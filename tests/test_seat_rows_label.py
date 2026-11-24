"""A row's own letter: at an end, hidden, or moved by hand (floorbit/blueprints/screen.py _row_labels)."""
import pytest

from floorbit import seat_rows
from floorbit.blueprints.screen import CELL


def _drawn(client, rows):
    block = client.post('/api/seat-blocks', json={'x': 50, 'y': 50, 'cols': 4, 'rows': 2, 'naming': 'rows',
                                                  'row_start': 'K'}).get_json()
    rows = [{**r, **more} for r, more in zip(block['rows'], rows, strict=True)]
    saved = client.put(f"/api/seat-blocks/{block['id']}", json={'rows': rows})
    assert saved.status_code == 200, saved.get_json()
    plan = client.get('/api/plan?hall=main').get_json()['drawing']
    return next(s for s in plan['shapes'] if s['id'] == block['id'])


def test_a_row_can_hide_its_letter_or_show_it_at_both_ends(client):
    shape = _drawn(client, [{'label': 'hidden'}, {'label': 'both'}])
    assert [(r['text'], r['r']) for r in shape['rows']] == [('L', 1), ('L', 1)]


def test_a_moved_letter_stays_where_it_was_put_in_the_row(client):
    shape = _drawn(client, [{'label': 'moved', 'label_at': [1.5, -1]}, {}])
    k = next(r for r in shape['rows'] if r['text'] == 'K')
    first = next(c for c in shape['cells'] if c['rc'] == [0, 0])
    # The first seat's centre is (0.5, 0.5) in the row's frame and a cell's x/y is its corner, so the
    # letter's centre is a seat right of that centre and a seat and a half up.
    assert (k['x'], k['y']) == pytest.approx((first['x'] + 1.5 * CELL, first['y'] - CELL))


def test_a_label_is_checked():
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean_row({'seats': 4, 'label': 'up'})
    with pytest.raises(seat_rows.RowError):
        seat_rows.clean_row({'seats': 4, 'label': 'moved', 'label_at': [1]})
    assert 'label_at' not in seat_rows.clean_row({'seats': 4, 'label': 'start', 'label_at': [1, 1]})
