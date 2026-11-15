"""What the local agent (bitsandbricks-ch/floorbit-agent) takes from Floorbit.

The agent runs Floorbit's plugins and flow collector instead of copying them, so every name it
imports from floorbit/ is a promise: renaming or removing one breaks the agent. This walks the
agent's source at AGENT_REF (tests/conftest.py) and checks each one still exists here."""
import ast
import importlib
import pathlib

import floorbit_agent


def floorbit_imports():
    """{(module, name)} for every import of floorbit code in the agent."""
    out = set()
    for path in pathlib.Path(floorbit_agent.__file__).parent.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "floorbit":
                out |= {(node.module, alias.name) for alias in node.names}
            elif isinstance(node, ast.Import):
                out |= {(a.name, None) for a in node.names if a.name.split(".")[0] == "floorbit"}
    return out


def test_everything_the_agent_takes_from_floorbit_is_still_here():
    found = floorbit_imports()
    assert found, "the walk found nothing: is the agent on the path?"
    for module, name in sorted(found, key=str):
        loaded = importlib.import_module(module)
        if name is not None:
            assert hasattr(loaded, name) or importlib.util.find_spec(f"{module}.{name}"), f"{module}.{name}"
