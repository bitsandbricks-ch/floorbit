"""docs/api-reference.md is written from the routes (issue #53): it must match them."""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_api_reference_matches_the_routes(app_module):
    spec = importlib.util.spec_from_file_location("api_reference", os.path.join(ROOT, "scripts", "api_reference.py"))
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    with open(script.OUT, encoding="utf-8") as f:
        assert f.read() == script.render(app_module.app), \
            "docs/api-reference.md is out of date: run python scripts/api_reference.py"
