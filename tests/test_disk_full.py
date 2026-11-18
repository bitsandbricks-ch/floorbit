"""A full or read-only disk: saves answer a clear 507, earlier data stays, other errors stay errors."""
import errno

import pytest

from floorbit import database


def _fail_writes(monkeypatch, message):
    """SQLite refusing every write the way it does on a full or read-only disk."""
    import sqlite3
    db = database.backend()
    real_run = db.run

    def refusing_run(sql, args=(), fetch=False):
        if sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
            raise database._failed(db, sqlite3.OperationalError(message))
        return real_run(sql, args, fetch)

    monkeypatch.setattr(db, 'run', refusing_run)


@pytest.mark.parametrize('message, kind', [('database or disk is full', 'disk_full'),
                                           ('attempt to write a readonly database', 'disk_read_only')])
def test_a_save_on_a_full_disk_says_so_and_keeps_what_was_saved(client, monkeypatch, message, kind):
    assert client.post('/api/teams', json={'name': 'Before'}).status_code == 201
    if database.backend().kind != 'sqlite':
        pytest.skip('a full disk under Postgres is the database server\'s')
    with monkeypatch.context() as full:   # not monkeypatch.undo(): that also drops conftest's patches
        _fail_writes(full, message)
        resp = client.post('/api/teams', json={'name': 'During'})
        assert resp.status_code == 507
        assert resp.get_json()['code'] == kind
        de = client.post('/api/teams', json={'name': 'During'}, headers={'Accept-Language': 'de-CH'})
        assert 'nicht gespeichert' in de.get_json()['error']
    names = [t['name'] for t in client.get('/api/teams').get_json()['teams']]
    assert 'Before' in names and 'During' not in names


def test_other_os_errors_are_left_to_the_server_error(app_module):
    from floorbit.blueprints.health import disk_unwritable
    with app_module.app.test_request_context('/api/x'):
        assert disk_unwritable(OSError(errno.ENOSPC, 'full')).status_code == 507
        with pytest.raises(FileNotFoundError):
            disk_unwritable(FileNotFoundError(errno.ENOENT, 'missing'))
