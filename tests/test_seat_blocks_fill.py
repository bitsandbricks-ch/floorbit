"""Fill area (floorbit/fill_area.py, #1565): a box filled with runs of seats and walkways."""
import pytest

from floorbit import fill_area

# 2 runs across and 2 down: runs of 10 seats plus the row letter (11 seats = 22 %), 2 rows with a
# 1 seat spacer (3 seats = 9.6 %), walkways 2 seats (4 % across, 6.4 % down).
BOX = {'x': 10, 'y': 10, 'w': 48, 'h': 25.6}


def test_layout_counts_runs_and_walkways():
    blocks, walkways = fill_area.layout(BOX, fill_area.options({}))
    assert len(blocks) == 4 and len(walkways) == 2
    assert [b['row_start'] for b in blocks] == ['A', 'C', 'E', 'G']
    # The first run's seats start one seat in (the letter) and its middle is 5 seats further.
    assert blocks[0]['x'] == pytest.approx(10 + 2 + 10) and blocks[0]['y'] == pytest.approx(10 + 1.5 * 3.2)
    assert blocks[1]['x'] == pytest.approx(10 + 22 + 4 + 2 + 10)
    across, down = walkways
    assert across['y'] == across['y2'] == pytest.approx(10 + 3 * 3.2 + 3.2)
    assert (across['x'], across['x2']) == (pytest.approx(10), pytest.approx(58))
    assert down['x'] == down['x2'] == pytest.approx(10 + 22 + 2) and across['width'] == 2


def test_no_walkway_puts_runs_back_to_back():
    blocks, walkways = fill_area.layout({**BOX, 'h': 19.2}, fill_area.options({'walkway': 0}))
    assert walkways == [] and len(blocks) == 4


def test_a_box_too_small_is_refused():
    with pytest.raises(fill_area.FillError):
        fill_area.layout({'x': 0, 'y': 0, 'w': 5, 'h': 5}, fill_area.options({}))


def test_fill_makes_blocks_walkways_and_a_group(client):
    res = client.post('/api/seat-blocks/fill', json={**BOX, 'group': 'Hall 1'})
    assert res.status_code == 201, res.get_json()
    out = res.get_json()
    assert len(out['blocks']) == 4 and len(out['marks']) == 2
    assert out['group']['name'] == 'Hall 1' and len(out['group']['members']) == 6
    assert out['blocks'][2]['row_letters'] == ['E', 'F']
    marks = client.get('/api/plan-marks').get_json()['marks']
    assert sum(m['kind'] == 'walkway' for m in marks) == 2


def test_preview_only_counts(client):
    out = client.post('/api/seat-blocks/fill', json={**BOX, 'preview': True}).get_json()
    assert out == {'blocks': 4, 'marks': 2, 'seats': 80}
    assert client.get('/api/seat-blocks').get_json() == []


def test_a_clash_changes_nothing(client):
    client.post('/api/seat-blocks', json={'cols': 4, 'rows': 1, 'x': 80, 'y': 80, 'naming': 'rows', 'row_start': 'C'})
    res = client.post('/api/seat-blocks/fill', json={**BOX, 'group': 'Hall 1'})
    assert res.status_code == 409
    assert len(client.get('/api/seat-blocks').get_json()) == 1
    assert client.get('/api/plan-marks').get_json()['marks'] == []


@pytest.mark.parametrize('bad', [
    {'seats': 0}, {'seats': 2.5}, {'rows': 'x'}, {'walkway': 0.2}, {'walkway': 30},
    {'spacer': -1}, {'row_start': '1'}, {'w': 'nan'}, {'x': None},
])
def test_bad_fills_are_refused(client, bad):
    assert client.post('/api/seat-blocks/fill', json={**BOX, **bad}).status_code == 400
