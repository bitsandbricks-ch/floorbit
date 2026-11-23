"""Every blueprint in this package, found by itself.

A new API area is a new module here with a ``bp``; it doesn't have to be added to a shared list.
That list (``ALL`` in ``__init__.py``) was the line every pull request with a new area edited, so
parallel ones conflicted on it. ``ALL`` keeps its order for the modules it names (issue #1232: drop
it once no open pull request adds to it); the rest follow sorted by name.
"""
import importlib
import pkgutil

from flask import Blueprint


def blueprints():
    from . import ALL, __path__
    from . import __name__ as package
    found = list(ALL)
    known = {id(bp) for bp in found}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith('_'):
            continue
        bp = getattr(importlib.import_module(f'{package}.{info.name}'), 'bp', None)
        if isinstance(bp, Blueprint) and id(bp) not in known:
            found.append(bp)
            known.add(id(bp))
    return found
