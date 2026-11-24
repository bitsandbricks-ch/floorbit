"""Each crew member's walk is kept (issue #1356): continued later, taken over by someone else, and
single seats marked. Demo hall, made-up crew names only."""
import time

from floorbit import seat_walkers
from tests.test_rbac import sign_in_as
from tests.test_seat_walk import demo_seat, hall, locate  # noqa: F401  # hall is a fixture
from tests.test_seat_walkers import _rows


def _walk(client, walk_id):
    return next(w for w in client.get('/api/seat-walk').get_json()['walks'] if w['id'] == walk_id)


def test_a_paused_walk_keeps_where_it_got_to_and_lets_its_rows_go(hall, app_module):  # noqa: F811
    row = _rows(hall)['A 1']
    me = hall.post('/api/seat-walk/walkers', json={'rows': [row], 'order': 'snake'}).get_json()
    assert me['user'] and me['order'] == 'snake' and me['active']
    ip = demo_seat('A-1')[0]
    assert locate(hall, 'A-1', ip, walker=me['id']).get_json()['ok']
    hall.put(f"/api/seat-walk/walkers/{me['id']}", json={'seat': 'A-2', 'failed': {'seat': 'A-2', 'why': 'no link'}})
    assert hall.put(f"/api/seat-walk/walkers/{me['id']}", json={'paused': True}).status_code == 200

    kept = _walk(hall, me['id'])
    assert not kept['active'] and kept['seat'] == 'A-2' and kept['rows'] == [row]
    assert [d['seat'] for d in kept['done']] == ['A-1'] and kept['failed']['A-2']['why'] == 'no link'
    # A paused walk doesn't hold its row: a row-mate can start on it.
    other = sign_in_as(app_module, 'walker2', 'lead')
    assert other.post('/api/seat-walk/walkers', json={'rows': [row]}).status_code == 201
    # ... and then that walk has it: continuing the old one says so.
    again = hall.put(f"/api/seat-walk/walkers/{me['id']}", json={'seat': 'A-2'})
    assert again.status_code == 404                                       # its only row went to walker2


def test_continue_after_a_break_on_any_device(hall, monkeypatch):  # noqa: F811
    row = _rows(hall)['B 1']
    me = hall.post('/api/seat-walk/walkers', json={'rows': [row]}).get_json()
    hall.put(f"/api/seat-walk/walkers/{me['id']}", json={'seat': 'B-5'})
    later = time.time() + seat_walkers.IDLE + 5
    monkeypatch.setattr(seat_walkers.time, 'time', lambda: later)
    body = hall.get('/api/seat-walk').get_json()
    walk = next(w for w in body['walks'] if w['id'] == me['id'])
    assert not walk['active'] and walk['user'] == body['me'] and walk['seat'] == 'B-5'
    by_row = {r['id']: r for r in body['hall']}
    assert by_row[row]['walker'] is None                                  # idle: nobody holds the row
    back = hall.put(f"/api/seat-walk/walkers/{me['id']}", json={'seat': 'B-5'}).get_json()
    assert back['active'] and back['rows'] == [row]


def test_someone_else_takes_a_walk_over_with_what_it_found(hall, app_module):  # noqa: F811
    row = _rows(hall)['C 1']
    me = hall.post('/api/seat-walk/walkers', json={'rows': [row]}).get_json()
    hall.put(f"/api/seat-walk/walkers/{me['id']}", json={'seat': 'C-3', 'failed': {'seat': 'C-2'}})
    other = sign_in_as(app_module, 'walker2', 'lead')
    took = other.post(f"/api/seat-walk/walkers/{me['id']}/take")
    assert took.status_code == 200
    walk = took.get_json()
    assert walk['who'] == 'walker2' and walk['taken_from'] and walk['seat'] == 'C-3' and 'C-2' in walk['failed']
    # The first walker's open page may not write to it any more.
    stale = hall.put(f"/api/seat-walk/walkers/{me['id']}", json={'seat': 'C-4'})
    assert stale.status_code == 409 and stale.get_json()['held'] == ['walker2']
    assert other.put(f"/api/seat-walk/walkers/{me['id']}", json={'seat': 'C-4'}).status_code == 200
    entries = hall.get('/api/settings/audit?area=check-in').get_json()['entries']
    assert any(e['action'] == 'Walk-through: walk taken over' for e in entries)


def test_marks_on_single_seats(hall, app_module):  # noqa: F811
    row = _rows(hall)['A 2']
    put = hall.put('/api/seat-walk/marks/a-13', json={'mark': 'broken', 'note': 'Socket hangs loose'})
    assert put.status_code == 200 and put.get_json()['mark'] == 'broken'
    assert hall.put('/api/seat-walk/marks/A-13', json={'mark': 'gone'}).status_code == 400
    assert hall.put('/api/seat-walk/marks/Z-99', json={'mark': 'later'}).status_code == 400
    body = hall.get(f'/api/seat-walk?rows={row}').get_json()
    seat = next(s for s in body['seats'] if s['seat'] == 'A-13')
    assert seat['mark']['note'] == 'Socket hangs loose' and body['marks']['A-13']['mark'] == 'broken'
    assert next(r for r in body['hall'] if r['id'] == row)['marked'] == 1
    viewer = sign_in_as(app_module, 'watcher', 'tech')
    assert viewer.put('/api/seat-walk/marks/A-14', json={'mark': 'later'}).status_code == 403
    assert hall.delete('/api/seat-walk/marks/A-13').status_code == 200
    assert hall.delete('/api/seat-walk/marks/A-13').status_code == 404


def test_undo_takes_the_seat_off_the_walk(hall):  # noqa: F811
    row = _rows(hall)['A 1']
    me = hall.post('/api/seat-walk/walkers', json={'rows': [row]}).get_json()
    assert locate(hall, 'A-1', demo_seat('A-1')[0], walker=me['id']).get_json()['ok']
    assert [d['seat'] for d in _walk(hall, me['id'])['done']] == ['A-1']
    assert hall.delete('/api/seat-walk/A-1').status_code == 200
    assert _walk(hall, me['id'])['done'] == []
