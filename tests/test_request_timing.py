"""Server-Timing on every answer, and a log line for slow requests (where the time goes)."""
import re

from floorbit import request_timing


def _timing(response):
    return dict(re.findall(r'(\w+);dur=([\d.]+)', response.headers.get('Server-Timing', '')))


def test_every_answer_says_where_its_time_went(client):
    r = client.get('/api/problems')
    assert r.status_code == 200
    t = _timing(r)
    assert {'total', 'cpu', 'db'} <= set(t)
    assert float(t['db']) <= float(t['total'])
    assert re.search(r'db;dur=[\d.]+;desc="\d+ quer(y|ies)"', r.headers['Server-Timing'])


def test_a_refused_request_is_timed_too(anon_client):
    r = anon_client.get('/api/problems')
    assert r.status_code == 401
    assert 'total' in _timing(r)


def test_database_work_is_counted(client, monkeypatch):
    from floorbit import database
    db = database.backend()
    db._stamps.clear()   # no copy to answer from: this read asks the database
    db._docs.clear()
    r = client.get('/api/problems')
    assert re.search(r'desc="([1-9]\d*) quer', r.headers['Server-Timing'])


def test_tiles_in_a_batch_count_for_the_batch(client):
    r = client.get('/api/dashboard/widgets?u=/api/dashboard/floorbit/problems&u=/api/dashboard/floorbit/problems')
    assert r.status_code == 200
    assert 'total' in _timing(r)
    assert request_timing._current.get() is None   # nothing left running after the request


def test_a_slow_request_is_logged_without_its_query_string(app_module, client, capsys):
    app_module.app.config['FLOORBIT_SLOW_REQUEST_MS'] = 0.0001
    try:
        client.get('/api/problems?k=secret-key')
    finally:
        app_module.app.config['FLOORBIT_SLOW_REQUEST_MS'] = 1000
    out = capsys.readouterr().out
    assert '[timing] Slow request: GET /api/problems 200 took' in out
    assert 'secret-key' not in out


def test_a_fast_request_is_not_logged(client, capsys):
    client.get('/api/auth/me')
    assert '[timing]' not in capsys.readouterr().out


def test_outside_a_request_database_work_is_not_counted():
    request_timing.note_db(1.0)   # a background thread: nothing to add to, nothing raised
    assert request_timing._current.get() is None
