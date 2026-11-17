"""Open live-update streams end when the worker stops, so a restart doesn't wait out the graceful timeout."""
import signal
import threading

import pytest

from integrations import events


@pytest.fixture(autouse=True)
def _reopen():
    yield
    events._closing.clear()


def test_close_all_ends_an_open_stream():
    gen = events.stream()
    assert next(gen).startswith('retry:')
    assert 'hello' in next(gen)
    done = threading.Event()

    def drain():
        for _ in gen:
            pass
        done.set()

    threading.Thread(target=drain, daemon=True).start()
    events.close_all()
    assert done.wait(5), 'the stream kept running after close_all()'
    assert events.client_count() == 0


def test_close_all_gets_through_a_full_queue():
    gen = events.stream()
    next(gen), next(gen)
    for i in range(events.CLIENT_QUEUE_SIZE):
        events.deliver_local({'id': i, 'type': 'x', 'data': {}})
    events.close_all()
    assert list(gen) == [], 'a stopping worker sends nothing more'


def test_sigterm_closes_streams_then_calls_the_server_handler():
    calls = []

    def server_handler(signum, frame):
        calls.append(('server', events._closing.is_set()))

    old = signal.signal(signal.SIGTERM, server_handler)
    try:
        assert events.close_streams_on_sigterm()
        assert not events.close_streams_on_sigterm(), 'wrapped twice'
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    finally:
        signal.signal(signal.SIGTERM, old)
    assert calls == [('server', True)]


def test_sigterm_default_is_left_alone():
    old = signal.signal(signal.SIGTERM, signal.SIG_DFL)
    try:
        assert not events.close_streams_on_sigterm()
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    finally:
        signal.signal(signal.SIGTERM, old)
