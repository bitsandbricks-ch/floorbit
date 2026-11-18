"""Live streams can't take every server thread (integrations/events.py, stream_limit): 64 open tabs
used to hold all 64 and no page loaded any more."""
import queue
import runpy
import types

import pytest

from integrations import events


@pytest.fixture
def threads(monkeypatch):
    """A server with 16 threads, and streams that are open already (fakes, not real tabs)."""
    monkeypatch.setenv(events.THREADS_ENV, "16")
    opened = []

    def open_streams(n, crew):
        for _ in range(n):
            q = queue.Queue()
            q.crew = crew
            opened.append(q)
            with events._lock:
                events._clients.add(q)

    yield open_streams
    with events._lock:
        for q in opened:
            events._clients.discard(q)


def test_a_quarter_of_the_threads_stays_for_pages(monkeypatch):
    for threads, limit in (("64", 48), ("200", 150), ("16", 8), ("8", None), ("", None), ("x", None)):
        monkeypatch.setenv(events.THREADS_ENV, threads)
        assert events.stream_limit() == limit, threads


def test_attendees_get_at_most_half_and_the_crew_the_rest(threads):
    threads(4, crew=False)
    assert not events.admit(crew=False)
    assert events.admit(crew=True)
    threads(4, crew=True)
    assert not events.admit(crew=True)


def test_a_stream_that_doesnt_fit_is_refused_clearly(threads, client, anon_client):
    threads(8, crew=True)
    resp = client.get("/api/events", headers={"Accept-Language": "de-CH"})
    assert resp.status_code == 503 and resp.headers["Retry-After"] == "30"
    assert resp.get_json()["code"] == "live_full"
    assert resp.get_json()["error"].startswith("Gerade bekommen zu viele")
    assert client.get("/api/plan").status_code == 200       # the pages themselves still load


def test_gunicorn_tells_floorbit_its_thread_count(monkeypatch):
    monkeypatch.setenv(events.THREADS_ENV, "0")         # put back as it was after the test
    conf = runpy.run_path("gunicorn.conf.py")
    conf["post_fork"](None, types.SimpleNamespace(cfg=types.SimpleNamespace(threads=64)))
    assert events.stream_limit() == 48
