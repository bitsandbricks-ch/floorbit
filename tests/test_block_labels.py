"""A block named by its rows has no name of its own: pickers and power feeds showed a dash and "?"
(Mike, 2026-11-19). They show the block's row letters instead."""
from floorbit import power, seat_names


def _rows_block(**extra):
    return {'id': 'b1', 'name': '', 'naming': 'rows', 'row_start': 'C', 'rows': 2, 'cols': 4, **extra}


def test_a_block_named_by_rows_is_called_by_its_row_letters():
    assert seat_names.label(_rows_block()) == 'C\u2013D'
    assert seat_names.label(_rows_block(rows=1)) == 'C'
    assert seat_names.label(_rows_block(rotation=180)) == 'C\u2013D'             # turned: still C to D
    assert seat_names.label({'name': 'A', 'rows': 2, 'cols': 4}) == 'A'
    assert seat_names.row_names(_rows_block()) == ['C', 'D']
    assert seat_names.row_names({'name': 'A', 'rows': 3}) == ['1', '2', '3']


def test_power_feeds_name_the_rows_not_a_question_mark():
    blocks = {'b1': _rows_block(), 'b2': {'id': 'b2', 'name': 'A', 'rows': 2, 'cols': 4}}
    assert power._feed_label({'block': 'b1', 'rows': [2]}, blocks) == 'row D'
    assert power._feed_label({'block': 'b1', 'rows': []}, blocks) == 'rows C\u2013D'
    assert power._feed_label({'block': 'b2', 'rows': [1, 2]}, blocks) == 'block A rows 1, 2'
    assert power._feed_label({'block': 'gone'}, blocks) == 'a removed block'


def test_the_blocks_api_gives_each_block_a_label(client):
    client.post('/api/seat-blocks', json={'name': '', 'naming': 'rows', 'row_start': 'E', 'x': 20, 'y': 20,
                                          'cols': 4, 'rows': 3})
    got = client.get('/api/seat-blocks').get_json()
    assert [(b['label'], b['row_names']) for b in got] == [('E\u2013G', ['E', 'F', 'G'])]
