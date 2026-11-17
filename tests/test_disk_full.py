"""A full or read-only disk: saves answer a clear 507, earlier data stays, other errors stay errors."""
import errno
import json

import pytest

from floorbit import database, store


def _fail_writes(monkeypatch, code):
    real_open = open

    def refusing_open(path, mode='r', *args, **kwargs):
        if any(m in mode for m in 'wa') and str(path).endswith(('.json', '.next')):
            raise OSError(code, errno.errorcode[code].lower(), str(path))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr('builtins.open', refusing_open)


@pytest.mark.parametrize('code, kind', [(errno.ENOSPC, 'disk_full'), (errno.EROFS, 'disk_read_only')])
def test_a_save_on_a_full_disk_says_so_and_keeps_what_was_saved(client, monkeypatch, code, kind):
    assert client.post('/api/teams', json={'name': 'Before'}).status_code == 201
    if database.backend().kind != 'files':
        pytest.skip('the database backends write elsewhere')
    with monkeypatch.context() as full:   # not monkeypatch.undo(): that also drops conftest's patches
        _fail_writes(full, code)
        resp = client.post('/api/teams', json={'name': 'During'})
        assert resp.status_code == 507
        assert resp.get_json()['code'] == kind
        de = client.post('/api/teams', json={'name': 'During'}, headers={'Accept-Language': 'de-CH'})
        assert 'nicht gespeichert' in de.get_json()['error']
    names = [t['name'] for t in client.get('/api/teams').get_json()['teams']]
    assert 'Before' in names
    with open(store.DATA_FILE) as f:
        json.load(f)   # never half a file


def test_other_os_errors_are_left_to_the_server_error(app_module):
    from floorbit.blueprints.health import disk_unwritable
    with app_module.app.test_request_context('/api/x'):
        assert disk_unwritable(OSError(errno.ENOSPC, 'full')).status_code == 507
        with pytest.raises(FileNotFoundError):
            disk_unwritable(FileNotFoundError(errno.ENOENT, 'missing'))
