"""What the local agent takes from the rest of Floorbit (floorbit/agent/README.md).

A new import from floorbit/ into the agent makes it harder to move to its own repository: add it to
the README's table and to ALLOWED here, on purpose."""
import ast
import pathlib

AGENT = pathlib.Path(__file__).resolve().parent.parent / "floorbit" / "agent"
ALLOWED = {"floorbit", "floorbit.sources", "floorbit.plugins.base", "floorbit.cables", "floorbit.dns",
           "floorbit.wifi", "floorbit.flows.collector"}
NAMES_FROM_FLOORBIT = {"ROOT", "create_app", "sources", "cables", "dns", "wifi"}


def floorbit_imports():
    """{(module, name)} for every import of floorbit code outside the agent package."""
    out = set()
    for path in AGENT.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                if node.level == 1 or (node.level == 0 and not (node.module or "").startswith("floorbit")):
                    continue        # the agent's own modules, or the standard library and requests
                base = "floorbit" + (f".{node.module}" if node.module and node.level == 2 else "")
                if node.level == 0:
                    base = node.module
                out |= {(base, alias.name) for alias in node.names}
            elif isinstance(node, ast.Import):
                out |= {(a.name, None) for a in node.names if a.name.startswith("floorbit")}
    return out


def test_the_agent_only_takes_what_its_readme_lists():
    found = floorbit_imports()
    assert found, "the walk found nothing: is AGENT the right folder?"
    assert {m for m, _ in found} <= ALLOWED
    assert {n for m, n in found if m == "floorbit"} <= NAMES_FROM_FLOORBIT


def test_the_readme_names_each_one():
    readme = (AGENT / "README.md").read_text()
    for module in ALLOWED - {"floorbit"}:
        assert f"`{module.removeprefix('floorbit.')}" in readme, module
