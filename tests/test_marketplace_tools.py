"""scripts/marketplace.py: signing a plugin release, building the signed index from GitHub releases
(a fake GitHub), and checking a published index, as floorbit-plugins' workflows run them."""
import importlib.util
import json
from pathlib import Path

import pytest

from floorbit.plugins import bundles

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("marketplace_tools", ROOT / "scripts" / "marketplace.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


@pytest.fixture
def keys(tmp_path, monkeypatch):
    out = {}
    for purpose in ("plugins", "index"):
        pem, pub = bundles.keygen()
        (tmp_path / "keys" / purpose).mkdir(parents=True)
        (tmp_path / "keys" / purpose / "k.pub").write_text(pub)
        (tmp_path / f"{purpose}.pem").write_bytes(pem)
        out[purpose] = tmp_path / f"{purpose}.pem"
    monkeypatch.setattr(bundles, "KEYS_DIR", tmp_path / "keys" / "plugins")
    monkeypatch.setattr(bundles, "INDEX_KEYS_DIR", tmp_path / "keys" / "index")
    return out


def plugin(tmp_path, version, pid="hallthing"):
    folder = tmp_path / "repo" / version
    (folder / "tests").mkdir(parents=True)
    (folder / "plugin.yaml").write_text(f"id: {pid}\nname: Hall thing\nversion: '{version}'\nfloorbit: '>=1.0'\n"
                                        "description: Shows the hall\nuses: [widgets]\n")
    (folder / "plugin.py").write_text("x = 1\n")
    (folder / "tests" / "test_x.py").write_text("def test(): pass\n")
    return folder


class FakeGitHub:
    def __init__(self, releases):
        self.rel = releases

    def repos(self, owner):
        return ["bitsandbricks-ch/floorbit-plugin-hallthing", "bitsandbricks-ch/floorbit"]

    def releases(self, repo):
        return self.rel.get(repo, [])

    def download(self, asset):
        return asset["data"]


def release(path, version, body=""):
    return {"tag_name": f"v{version}", "published_at": "2026-11-17T12:00:00Z", "body": body,
            "assets": [{"name": path.name, "url": "x", "data": path.read_bytes()}]}


def test_sign_build_and_check(tmp_path, keys):
    pem = keys["plugins"].read_bytes()
    a = tools.sign_folder(plugin(tmp_path, "1.0.0"), pem, "1.0.0", tmp_path / "dist")
    b = tools.sign_folder(plugin(tmp_path, "1.1.0"), pem, "1.1.0", tmp_path / "dist")
    assert a.name == "hallthing-1.0.0.tar.gz"
    bundles.unpack(a.read_bytes(), tmp_path / "x")
    assert not (tmp_path / "x" / "tests").exists()                 # the release is the plugin, not its tests
    repo = "bitsandbricks-ch/floorbit-plugin-hallthing"
    gh = FakeGitHub({repo: [release(b, "1.1.0", "Faster."), release(a, "1.0.0")]})
    config = {"name": "Floorbit Marketplace", "discover": [{"owner": "bitsandbricks-ch", "prefix": "floorbit-plugin-"}],
              "plugins": [{"repo": repo, "withdrawn": {"1.0.0": "broke the widget"}}]}
    doc = tools.build_index(config, tmp_path / "site", keys["index"].read_bytes(), gh, log=lambda *_: None)
    entry = doc["plugins"][0]
    assert (entry["id"], entry["name"], entry["repository"]) == ("hallthing", "Hall thing", repo)
    assert [(v["version"], v.get("withdrawn"), v["floorbit"]) for v in entry["versions"]] == [
        ("1.1.0", None, ">=1.0"), ("1.0.0", "broke the widget", ">=1.0")]
    assert entry["versions"][0]["changes"] == "Faster."
    served = {p.name: p.read_bytes() for p in (tmp_path / "site").iterdir()}
    assert sorted(served) == ["hallthing-1.0.0.tar.gz", "hallthing-1.1.0.tar.gz", "index.json"]
    base = "https://plugins.example.com/"
    assert tools.check(base + "index.json", lambda u: served[u.removeprefix(base)], log=lambda *_: None) == 0
    served["hallthing-1.1.0.tar.gz"] = served["hallthing-1.0.0.tar.gz"]
    assert tools.check(base + "index.json", lambda u: served[u.removeprefix(base)], log=lambda *_: None) == 1


def test_an_unsigned_or_foreign_release_is_left_out(tmp_path, keys):
    stranger, _ = bundles.keygen()
    bad = tools.sign_folder(plugin(tmp_path, "2.0.0"), stranger, "2.0.0", tmp_path / "dist")
    repo = "bitsandbricks-ch/floorbit-plugin-hallthing"
    doc = tools.build_index({"plugins": [{"repo": repo}]}, tmp_path / "site", keys["index"].read_bytes(),
                            FakeGitHub({repo: [release(bad, "2.0.0")]}), log=lambda *_: None)
    assert doc["plugins"] == []
    assert not (tmp_path / "site" / "hallthing-2.0.0.tar.gz").exists()


def test_keys_have_one_purpose(tmp_path, keys):
    with pytest.raises(SystemExit, match="not the index key"):
        tools._private(keys["plugins"], "index")
    with pytest.raises(SystemExit, match="not the plugins key"):
        tools._private(keys["index"], "plugins")
    (tmp_path / "keys" / "index" / "same.pub").write_text((tmp_path / "keys" / "plugins" / "k.pub").read_text())
    with pytest.raises(SystemExit, match="one purpose"):
        tools._private(keys["plugins"], "plugins")


def test_the_tag_must_match_plugin_yaml(tmp_path, keys):
    with pytest.raises(SystemExit, match="the tag"):
        tools.sign_folder(plugin(tmp_path, "1.0.0"), keys["plugins"].read_bytes(), "1.0.1", tmp_path / "dist")


def test_the_index_floorbit_reads(tmp_path, keys):
    """What build_index writes is what floorbit/marketplace.py takes."""
    from floorbit import marketplace
    a = tools.sign_folder(plugin(tmp_path, "1.0.0"), keys["plugins"].read_bytes(), "1.0.0", tmp_path / "dist")
    repo = "bitsandbricks-ch/floorbit-plugin-hallthing"
    doc = tools.build_index({"plugins": [{"repo": repo}]}, tmp_path / "site", keys["index"].read_bytes(),
                            FakeGitHub({repo: [release(a, "1.0.0")]}), log=lambda *_: None)
    doc = json.loads((tmp_path / "site" / "index.json").read_text())
    bundles.verify_index(doc, bundles.pinned_keys(bundles.INDEX_KEYS_DIR))
    assert marketplace.versions_of(doc["plugins"][0])[0]["file"] == "hallthing-1.0.0.tar.gz"


def test_a_signed_release_floorbit_would_refuse_is_not_listed(tmp_path, keys):
    folder = plugin(tmp_path, "1.0.0")
    (folder / "plugin.yaml").write_text("id: hallthing\nname: Hall thing\nversion: '1.0.0'\nuses: [root]\n")
    bad = tools.sign_folder(folder, keys["plugins"].read_bytes(), "1.0.0", tmp_path / "dist")
    repo = "bitsandbricks-ch/floorbit-plugin-hallthing"
    lines = []
    doc = tools.build_index({"plugins": [{"repo": repo}]}, tmp_path / "site", keys["index"].read_bytes(),
                            FakeGitHub({repo: [release(bad, "1.0.0")]}), log=lines.append)
    assert doc["plugins"] == []
    assert any("unknown area" in line for line in lines)


AGENT_YAML = """id: hallthing
name: Hall thing
icon: storage
version: '1.0.0'
uses: [agent, actions, widgets, settings]
settings:
  - {key: token, type: secret}
actions:
  - {id: clear, role: admin, danger: true}
widgets:
  - {id: tile, permission: seats.view}
agent:
  sends: {stats: {privacy: aggregate}, devices: {privacy: device}}
  actions: [clear]
  targets: {credentials: [ssh]}
"""


def test_the_index_says_what_each_version_may_touch(tmp_path, keys):
    from floorbit import marketplace
    folder = plugin(tmp_path, "1.0.0")
    (folder / "plugin.yaml").write_text(AGENT_YAML)
    (folder / "plugin.py").write_text(
        "from floorbit.plugins.base import Plugin as B\nclass Plugin(B):\n"
        "    def run_clear(self, p): pass\n    def widget_tile(self): pass\n")
    (folder / "agent.py").write_text("x = 1\n")
    signed = tools.sign_folder(folder, keys["plugins"].read_bytes(), "1.0.0", tmp_path / "dist")
    repo = "bitsandbricks-ch/floorbit-plugin-hallthing"
    doc = tools.build_index({"plugins": [{"repo": repo}]}, tmp_path / "site", keys["index"].read_bytes(),
                            FakeGitHub({repo: [release(signed, "1.0.0")]}), log=lambda *_: None)
    assert doc["plugins"][0]["icon"] == "storage"
    got = marketplace.versions_of(doc["plugins"][0])[0]["touches"]
    assert got == {"uses": ["agent", "actions", "widgets", "settings"],
                   "permissions": ["seats.view", "settings.manage"],
                   "secrets": 1, "sends": {"stats": "aggregate", "devices": "device"}, "hall_actions": ["clear"],
                   "credentials": ["ssh"]}


def test_touches_from_an_index_are_cut_to_what_floorbit_knows():
    from floorbit.plugins import clean_touches
    assert clean_touches(None) is None
    got = clean_touches({"uses": ["agent", "root", "<b>"], "permissions": ["god.mode", "seats.view"],
                         "secrets": "-3", "sends": {"x": "everything", "y": "device"},
                         "hall_actions": ["ok", "../x"], "credentials": ["ssh", "telnet"]})
    assert got == {"uses": ["agent"], "permissions": ["seats.view"], "secrets": 0, "sends": {"y": "device"},
                   "hall_actions": ["ok"], "credentials": ["ssh"]}


def test_floorbits_rules_file_is_built_checked_and_signed(tmp_path, keys):
    """build-applications writes what a Floorbit's rule source takes (#1504)."""
    from floorbit import application_sources
    games = {"applications": [{"id": "example-arena", "name": "Example Arena", "kind": "game",
                               "sites": ["arena.example.com"], "ports": ["udp/7777"]}]}
    tools.build_applications(games, tmp_path / "site", keys["index"].read_bytes())
    raw = (tmp_path / "site" / "applications.json").read_bytes()
    doc = bundles.verify_rules(json.loads(raw), bundles.pinned_keys(bundles.INDEX_KEYS_DIR))
    assert doc["kind"] == "floorbit-applications" and doc["applications"][0]["sites"] == ["example.com"]
    got = application_sources.parse(raw, application_sources.FLOORBIT)
    assert [a["id"] for a in got] == ["example-arena"]
    # A changed file, or the index key's signature over an index, doesn't pass as a rules file.
    tampered = json.loads(raw)
    tampered["applications"][0]["ports"] = ["udp/1-65535"]
    with pytest.raises(application_sources.SourceError, match="bad rules file signature"):
        application_sources.parse(json.dumps(tampered).encode(), application_sources.FLOORBIT)
    index = bundles.sign_index({"name": "x", "plugins": []}, keys["index"].read_bytes())
    with pytest.raises(application_sources.SourceError, match="not signed"):
        application_sources.parse(json.dumps(index).encode(), application_sources.FLOORBIT)
    # An unsigned file in the right shape is refused too.
    with pytest.raises(application_sources.SourceError, match="not signed"):
        application_sources.parse(json.dumps({"version": 1, "applications": []}).encode(),
                                  application_sources.FLOORBIT)


def test_a_bad_games_file_stops_the_build(tmp_path, keys):
    with pytest.raises(SystemExit, match=r"games\.yaml"):
        tools.build_applications({"applications": [{"id": "x", "name": "X", "ports": ["udp/99999"]}]},
                                 tmp_path / "site", keys["index"].read_bytes())
    assert not (tmp_path / "site" / "applications.json").exists()


def test_the_rules_file_needs_the_index_key(tmp_path, keys):
    with pytest.raises(SystemExit, match="not the index key"):
        tools._private(keys["plugins"], "index")
