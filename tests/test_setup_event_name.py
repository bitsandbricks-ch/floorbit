"""Set up's first step counts the event's own name (issue #1437), and sends an unnamed event (the
sidebar shows it as "First event") to Events to name it."""
from floorbit import setup


class _Settings(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def test_the_event_name_counts():
    steps = {s['id']: s for s in setup.checklist({}, _Settings(), event_name='First event')}
    event = steps['event']
    assert event['facts']['name'] is True and event['facts']['dates'] is False
    assert event['state'] == 'look' and event['href'] == '/schedule'


def test_no_name_anywhere_sends_to_events():
    steps = {s['id']: s for s in setup.checklist({}, _Settings())}
    assert steps['event']['facts']['name'] is False and steps['event']['href'] == '/events'


def test_the_api_passes_the_events_name(client):
    steps = {s['id']: s for s in client.get('/api/setup/checklist').get_json()['steps']}
    assert steps['event']['facts']['name'] is False      # the first event has no name of its own yet
    assert steps['event']['href'] == '/events'
