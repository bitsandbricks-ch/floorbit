"""Blueprints register themselves (floorbit/blueprints/_discover.py): a new area is a new module,
not a line in a shared list that parallel pull requests all edit."""
import importlib
import pkgutil

from flask import Blueprint

from floorbit import blueprints as package
from floorbit.blueprints._discover import blueprints


def test_every_module_with_a_blueprint_is_registered(app_module):
    registered = set(app_module.app.blueprints.values())
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith('_'):
            continue
        bp = getattr(importlib.import_module(f'floorbit.blueprints.{info.name}'), 'bp', None)
        if isinstance(bp, Blueprint):
            assert bp in registered, f'floorbit/blueprints/{info.name}.py has a bp that is not registered'


def test_each_blueprint_once():
    found = blueprints()
    assert len(found) == len({id(bp) for bp in found})


def test_no_two_views_answer_the_same_address(app_module):
    # The order blueprints register in no longer says which one wins, so none may compete.
    seen, clashes = {}, []
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            key = (rule.rule, method)
            if key in seen and seen[key] != rule.endpoint:
                clashes.append(f'{method} {rule.rule}: {seen[key]} and {rule.endpoint}')
            seen.setdefault(key, rule.endpoint)
    assert not clashes, 'Two views answer the same address:\n' + '\n'.join(clashes)
