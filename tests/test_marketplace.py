"""The plugin Marketplace (floorbit/marketplace.py): signed index and bundles, trust levels, install,
update, rollback, withdrawn versions, removal, other instances catching up, and the agents' share."""
import json

import pytest
import requests

from floorbit import marketplace
from floorbit.plugins import bundles

URL = "https://plugins.example.com/index.json"


class Answer:
    def __init__(self, body, status=200):
        self.content, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return json.loads(self.content)

    # what a streamed get uses (marketplace._get_capped)
    @property
    def headers(self):
        return {}

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def market(tmp_path, monkeypatch, app_module):
    """An official index at URL with keys pinned for it, and a place to publish versions."""
    plugin_pem, plugin_pub = bundles.keygen()
    index_pem, index_pub = bundles.keygen()
    (tmp_path / "keys" / "plugins").mkdir(parents=True)
    (tmp_path / "keys" / "index").mkdir()
    (tmp_path / "keys" / "plugins" / "release.pub").write_text(plugin_pub)
    (tmp_path / "keys" / "index" / "index.pub").write_text(index_pub)
    monkeypatch.setattr(bundles, "KEYS_DIR", tmp_path / "keys" / "plugins")
    monkeypatch.setattr(bundles, "INDEX_KEYS_DIR", tmp_path / "keys" / "index")
    monkeypatch.setenv("FLOORBIT_MARKETPLACE_URL", URL)
    monkeypatch.setenv("FLOORBIT_PLUGIN_DIR", str(tmp_path / "installed"))
    monkeypatch.delenv("FLOORBIT_MARKETPLACE_SOURCES", raising=False)
    monkeypatch.delenv("FLOORBIT_COMMUNITY_KEYS", raising=False)
    marketplace._cache.clear()
    files, entries = {}, {}

    def publish(pid, version, pem=plugin_pem, withdrawn="", floorbit="", body="x = 1\n", base=URL, index=None,
                icon=None, uses="widgets", extra=""):
        src = tmp_path / "src" / f"{pid}-{version}"
        src.mkdir(parents=True)
        (src / "plugin.yaml").write_text(
            f"id: {pid}\nname: Hall thing\nversion: '{version}'\nuses: [{uses}]\n"
            "widgets: [{id: load, label: Load}]\n" + extra)
        (src / "plugin.py").write_text(
            "from floorbit.plugins import Plugin\n\n\nclass Plugin(Plugin):\n"
            f"    def widget_load(self):\n        return {{'type': 'stat', 'value': '{version}'}}\n" + body)
        bundles.sign(src, pem, version, 1)
        data = bundles.pack(src)
        name = f"{pid}-{version}.tar.gz"
        files[base.rsplit("/", 1)[0] + "/" + name] = data
        doc = entries.setdefault(index or base, {})
        doc.setdefault(pid, {"id": pid, "name": "Hall thing", "description": "Shows the hall", "versions": []})
        if icon is not None:
            doc[pid]["icon"] = icon
        doc[pid]["versions"].append({"version": version, "file": name, "sha256": bundles.sha256(data),
                                     "floorbit": floorbit, "agent_api": 1, "withdrawn": withdrawn})
        sign_all()
        return data

    def sign_all(pem=index_pem):
        for url, doc in entries.items():
            signed = bundles.sign_index({"name": "Example market", "generated": "2026-11-17",
                                         "plugins": list(doc.values())}, pem)
            files[url] = json.dumps(signed).encode()
        marketplace._cache.clear()

    def get(url, timeout=None, **kw):
        return Answer(files[url]) if url in files else Answer(b"", 404)

    monkeypatch.setattr(requests, "get", get)
    registry = app_module.app.extensions["floorbit_plugins"]
    yield type("Market", (), {"publish": staticmethod(publish), "files": files, "sign_all": staticmethod(sign_all),
                              "registry": registry, "tmp": tmp_path, "index_pem": index_pem})
    for pid in [s.id for s in registry.specs.values() if s.trust in marketplace.TRUST_RANK]:
        registry.drop(pid)


def test_install_update_rollback_and_remove(client, market):
    market.publish("hallthing", "1.0.0")
    page = client.get("/api/settings/marketplace").get_json()
    assert page["sources"] == [{"url": URL, "official": True, "name": "Example market", "generated": "2026-11-17",
                                "error": ""}]
    entry = page["plugins"][0]
    assert (entry["id"], entry["installed"], entry["best"], entry["trust"]) == ("hallthing", None, "1.0.0", "official")

    res = client.post("/api/settings/marketplace/hallthing", json={})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["version"] == "1.0.0" and res.get_json()["trust"] == "official"
    spec = market.registry.specs["hallthing"]
    assert spec.trust == "official" and not spec.error
    assert not market.registry.enabled(spec)                      # installed means off until an admin turns it on
    assert client.post("/api/settings/marketplace/hallthing", json={}).status_code == 400   # already there

    market.publish("hallthing", "1.1.0")
    entry = client.get("/api/settings/marketplace?refresh=1").get_json()["plugins"][0]
    assert entry["update"] == "1.1.0"
    assert client.post("/api/settings/marketplace/hallthing", json={}).get_json()["previous"] == "1.0.0"
    assert market.registry.specs["hallthing"].path.name == "1.1.0"

    back = client.post("/api/settings/marketplace/hallthing/rollback").get_json()
    assert (back["version"], back["previous"]) == ("1.0.0", "1.1.0")
    assert market.registry.specs["hallthing"].path.name == "1.0.0"

    assert client.delete("/api/settings/marketplace/hallthing").status_code == 200
    assert "hallthing" not in market.registry.specs
    assert not (market.tmp / "installed" / "hallthing").exists()
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    for text in ("Installed plugin hallthing 1.0.0", "Updated plugin hallthing from 1.0.0 to 1.1.0",
                 "Rolled back plugin hallthing from 1.1.0 to 1.0.0", "Removed plugin hallthing 1.0.0"):
        assert text in actions


def test_withdrawn_and_incompatible_versions_are_not_installed(client, market):
    market.publish("hallthing", "1.0.0")
    market.publish("hallthing", "1.1.0", withdrawn="breaks the widget")
    market.publish("hallthing", "2.0.0", floorbit=">=999")
    entry = client.get("/api/settings/marketplace").get_json()["plugins"][0]
    assert entry["best"] == "1.0.0"
    assert [v["compatible"] for v in entry["versions"]] == [False, True, True]
    res = client.post("/api/settings/marketplace/hallthing", json={"version": "1.1.0"})
    assert res.status_code == 400 and "withdrawn" in res.get_json()["error"]
    res = client.post("/api/settings/marketplace/hallthing", json={"version": "2.0.0"})
    assert res.status_code == 400 and "needs Floorbit" in res.get_json()["error"]
    assert client.post("/api/settings/marketplace/hallthing", json={}).get_json()["version"] == "1.0.0"


def test_nothing_unsigned_or_tampered_gets_in(client, market):
    stranger, _ = bundles.keygen()
    market.publish("hallthing", "1.0.0", pem=stranger)            # a plugin key nobody pinned
    res = client.post("/api/settings/marketplace/hallthing", json={})
    assert res.status_code == 400 and "does not trust" in res.get_json()["error"]
    assert "hallthing" not in market.registry.specs

    market.publish("other", "1.0.0")
    url = URL.rsplit("/", 1)[0] + "/other-1.0.0.tar.gz"
    market.files[url] = market.files[url][:-8] + b"tampered"     # not what the index lists
    res = client.post("/api/settings/marketplace/other", json={})
    assert res.status_code == 400 and "does not match" in res.get_json()["error"]

    market.sign_all(pem=stranger)                                  # an index signed by someone else
    page = client.get("/api/settings/marketplace").get_json()
    assert "does not trust" in page["sources"][0]["error"] and page["plugins"] == []


def test_builtin_plugins_are_not_replaced(client, market):
    market.publish("lancache", "9.0.0")
    res = client.post("/api/settings/marketplace/lancache", json={})
    assert res.status_code == 400 and "ships with this Floorbit" in res.get_json()["error"]
    assert market.registry.specs["lancache"].trust == "builtin"


def test_a_plugin_that_fails_to_load_leaves_the_old_one_running(client, market):
    market.publish("hallthing", "1.0.0")
    client.post("/api/settings/marketplace/hallthing", json={})
    market.publish("hallthing", "1.1.0", body="raise RuntimeError('broken')\n")
    res = client.post("/api/settings/marketplace/hallthing", json={})
    assert res.status_code == 400 and "does not load" in res.get_json()["error"]
    assert market.registry.specs["hallthing"].path.name == "1.0.0"
    assert marketplace.installed()["hallthing"]["version"] == "1.0.0"


MIGRATE = """
    def migrate(self, from_schema, store):
        if {fail}:
            raise RuntimeError('no')
        store.collection('notes').put('n', {{'schema': {schema}, 'from': from_schema}})
"""


def test_an_update_whose_migration_fails_leaves_the_old_one_running(client, market):
    market.publish("hallthing", "1.0.0", uses="widgets, documents", extra="schema: 1\n",
                   body=MIGRATE.format(fail=False, schema=1))
    client.post("/api/settings/marketplace/hallthing", json={})
    assert market.registry.schema_of("hallthing") == 1            # moved on install
    market.publish("hallthing", "1.1.0", uses="widgets, documents", extra="schema: 2\n",
                   body=MIGRATE.format(fail=True, schema=2))
    res = client.post("/api/settings/marketplace/hallthing", json={})
    assert res.status_code == 400 and "could not move its data from schema 1 to 2" in res.get_json()["error"]
    assert market.registry.specs["hallthing"].path.name == "1.0.0"
    assert marketplace.installed()["hallthing"]["version"] == "1.0.0"
    assert market.registry.schema_of("hallthing") == 1


def test_no_rollback_to_a_version_that_cant_read_the_data(client, market):
    market.publish("hallthing", "1.0.0", uses="widgets, documents", extra="schema: 1\n",
                   body=MIGRATE.format(fail=False, schema=1))
    client.post("/api/settings/marketplace/hallthing", json={})
    market.publish("hallthing", "1.1.0", uses="widgets, documents", extra="schema: 2\n",
                   body=MIGRATE.format(fail=False, schema=2))
    assert client.post("/api/settings/marketplace/hallthing", json={}).status_code == 200
    assert market.registry.schema_of("hallthing") == 2
    res = client.post("/api/settings/marketplace/hallthing/rollback")
    assert res.status_code == 400 and "can't read the data 1.1.0 moved to schema 2" in res.get_json()["error"]
    assert market.registry.specs["hallthing"].path.name == "1.1.0"


def test_community_sources_need_the_operators_key(client, market, monkeypatch):
    other = "https://community.example.org/index.json"
    pem, pub = bundles.keygen()
    monkeypatch.setenv("FLOORBIT_MARKETPLACE_SOURCES", other)
    market.publish("partything", "0.1.0", pem=pem, base=other, index=other)
    signed = bundles.sign_index({"name": "Community", "generated": "x",
                                 "plugins": [json.loads(market.files[other])["plugins"][0]]}, pem)
    market.files[other] = json.dumps(signed).encode()
    marketplace._cache.clear()
    page = client.get("/api/settings/marketplace").get_json()
    assert "does not trust" in page["sources"][1]["error"]          # no key in FLOORBIT_COMMUNITY_KEYS yet

    keys = market.tmp / "community"
    keys.mkdir()
    (keys / "friend.pub").write_text(pub)
    monkeypatch.setenv("FLOORBIT_COMMUNITY_KEYS", str(keys))
    marketplace._cache.clear()
    page = client.get("/api/settings/marketplace").get_json()
    entry = next(p for p in page["plugins"] if p["id"] == "partything")
    assert entry["trust"] == "community"
    assert client.post("/api/settings/marketplace/partything", json={}).get_json()["trust"] == "community"
    assert market.registry.specs["partything"].trust == "community"
    assert "partything" not in marketplace.agent_bundles()           # the agents trust only official plugins


def test_another_instance_catches_up(client, market):
    market.publish("hallthing", "1.0.0")
    client.post("/api/settings/marketplace/hallthing", json={})
    import shutil
    shutil.rmtree(market.tmp / "installed")                       # a second pod: same database, empty disk
    market.registry.drop("hallthing")
    marketplace.sync(market.registry)
    assert market.registry.specs["hallthing"].path.name == "1.0.0"
    marketplace.uninstall(market.registry, "hallthing")
    market.registry.specs["hallthing"] = market.registry.add(market.tmp / "src" / "hallthing-1.0.0", "official")
    marketplace.sync(market.registry)                              # removed elsewhere: gone here too
    assert "hallthing" not in market.registry.specs


def test_official_plugins_go_to_the_agents(client, market, anon_client):
    data = market.publish("hallthing", "1.0.0")
    client.post("/api/settings/marketplace/hallthing", json={})
    offered = marketplace.agent_bundles()["hallthing"]
    assert offered == {"version": "1.0.0", "file": "hallthing-1.0.0.tar.gz", "sha256": bundles.sha256(data),
                       "agent_api": 1}
    from floorbit import agent_plugins
    assert agent_plugins.bundles_offer({"hallthing"}) == {"hallthing": offered}
    assert agent_plugins.bundle_file("hallthing-1.0.0.tar.gz").read_bytes() == data
    assert agent_plugins.bundle_file("hallthing-9.0.0.tar.gz") is None


def test_index_signature(market):
    pem = market.index_pem
    keys = bundles.pinned_keys(bundles.INDEX_KEYS_DIR)
    doc = bundles.sign_index({"name": "x", "plugins": []}, pem)
    assert bundles.verify_index(doc, keys) is doc
    with pytest.raises(bundles.BundleError, match="bad index signature"):
        bundles.verify_index({**doc, "plugins": [{"id": "evil"}]}, keys)
    with pytest.raises(bundles.BundleError, match="not signed"):
        bundles.verify_index({"plugins": []}, keys)


def test_only_admins(client, app_module):
    app_module.app.extensions["auth"].users.add("viewer1", "pw-viewer-1", role="viewer")
    other = app_module.app.test_client()
    other.post("/login", data={"username": "viewer1", "password": "pw-viewer-1"})
    assert other.get("/api/settings/marketplace").status_code == 403
    assert other.post("/api/settings/marketplace/hallthing", json={}).status_code == 403
