"""Where a request's time goes: a ``Server-Timing`` header on every answer, and a log line for slow ones.

The browser shows the header in its network panel and keeps it in a HAR export, so a slow page can
be read without access to the server: ``total`` is the time inside Floorbit, ``cpu`` the part this
thread computed, ``db`` the part spent with the database (``pool`` of it waiting for a free
connection). What the browser measured on top of ``total`` was spent on the way: the proxy, the
network, or waiting for a free gunicorn thread.

A request that takes longer than ``FLOORBIT_SLOW_REQUEST_MS`` (1000) is logged with the same numbers
(method and path only: the query string can hold a key). See docs/install.md.
"""
import time
from contextvars import ContextVar

from flask import g, request

from .env import number

SLOW_ENV = 'FLOORBIT_SLOW_REQUEST_MS'

# Per request: [db seconds, statements, pool wait seconds]. Tiles answered inside a batch request
# (blueprints/widget_batch.py) run in the same thread and add to the batch's numbers.
_current = ContextVar('floorbit_request_timing', default=None)


def note_db(seconds, waited=0.0):
    """Called by the database for each borrowed connection: the time it was held, and the wait for it."""
    spent = _current.get()
    if spent is not None:
        spent[0] += seconds
        spent[1] += 1
        spent[2] += waited


def _ms(seconds):
    return round(seconds * 1000, 1)


def _queries(n):
    return 'query' if n == 1 else 'queries'


def init_request_timing(app):
    app.config['FLOORBIT_SLOW_REQUEST_MS'] = number(SLOW_ENV, 1000, minimum=0)

    def start():
        if _current.get() is not None:   # a tile inside a batch: the batch counts it
            return
        g._timing = (time.perf_counter(), time.thread_time(), _current.set([0.0, 0, 0.0]))

    def finish(response):
        timing = g.pop('_timing', None)
        if timing is None:
            return response
        started, cpu_started, token = timing
        total = time.perf_counter() - started
        cpu = time.thread_time() - cpu_started
        db, statements, waited = _current.get()
        _current.reset(token)
        parts = [f'total;dur={_ms(total)}', f'cpu;dur={_ms(cpu)}',
                 f'db;dur={_ms(db)};desc="{statements} {_queries(statements)}"']
        if waited >= 0.0005:
            parts.append(f'pool;dur={_ms(waited)}')
        response.headers['Server-Timing'] = ', '.join(parts)
        slow_ms = app.config['FLOORBIT_SLOW_REQUEST_MS']
        if slow_ms and total * 1000 >= slow_ms:
            print(f'[timing] Slow request: {request.method} {request.path} {response.status_code} took '
                  f'{total * 1000:.0f} ms (cpu {cpu * 1000:.0f} ms, database {db * 1000:.0f} ms for {statements} '
                  f'{_queries(statements)}, {waited * 1000:.0f} ms of it waiting for a connection)', flush=True)
        return response

    def forget(_exc=None):
        # An answer that failed before after_request: don't leave the counter running into the next one.
        timing = g.pop('_timing', None)
        if timing is not None:
            _current.reset(timing[2])

    app.extensions['floorbit_request_timing'] = start
    app.before_request(start)
    app.after_request(finish)
    app.teardown_request(forget)


def start_first(app):
    """Move the start to the front, once every other hook is registered: sign-in and the other
    checks count too (some hooks put themselves first, so registering it first isn't enough)."""
    start = app.extensions['floorbit_request_timing']
    hooks = app.before_request_funcs.setdefault(None, [])
    hooks.remove(start)
    hooks.insert(0, start)
