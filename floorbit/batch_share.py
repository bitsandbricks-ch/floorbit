"""Data sources read once per batch of dashboard tiles (issue #1300).

Many tiles draw from the same source: five read the traffic snapshot, four the flow summary, three
the DNS counts. Inside ``GET /api/dashboard/widgets`` each source runs once and every tile that
asks gets the same answer. Outside a batch nothing is kept. The answers are shared: read them, don't
change them.
"""
import contextvars
import functools
from contextlib import contextmanager

_shared = contextvars.ContextVar('floorbit_batch_share', default=None)


@contextmanager
def batch():
    """Sources read inside this block are read once."""
    token = _shared.set({})
    try:
        yield
    finally:
        _shared.reset(token)


def once_per_batch(fn):
    """``fn``'s answer is kept for the rest of the batch. The key is the function, not its
    arguments: every tile of a batch asks as the same account, in the same language."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        kept = _shared.get()
        if kept is None:
            return fn(*args, **kwargs)
        if fn not in kept:
            kept[fn] = fn(*args, **kwargs)
        return kept[fn]
    return wrapper
