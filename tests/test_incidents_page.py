"""One incident's page (issue #887): served to the board's people, refused to anyone else."""
from tests.test_incidents import sign_in_as


def test_an_incident_has_its_own_page(client):
    assert client.get('/incidents/abc123').status_code == 200


def test_the_page_needs_the_board(app_module):
    viewer = sign_in_as(app_module, 'viewer1', 'viewer')
    assert viewer.get('/incidents/abc123').status_code == 403
