"""A plugin's own JSON documents (``uses: [documents]``) and ``schema:`` with ``migrate``."""
import threading
import time

import pytest
from test_plugins import write_plugin

from floorbit import store
from floorbit.plugins import PluginError, _load, documents, validate

YAML = """
id: docthing
name: Doc thing
version: "2.0"
uses: [documents, storage, actions]
schema: 2
actions:
  - {id: noop}
"""

PY = """
import time
from floorbit.plugins.base import Plugin as Base

CALLS = []
FAIL = []
SLEEP = []

class Plugin(Base):
    def migrate(self, from_schema, store):
        CALLS.append(from_schema)
        if SLEEP:
            time.sleep(SLEEP[0])
        if FAIL:
            raise RuntimeError('boom')
        notes = store.collection('notes')
        for doc_id, doc in notes.all().items():
            notes.put(doc_id, {'text': doc.get('text', doc.get('old', '')), 'v': 2})
        store.set_state('migrated_from', from_schema)

    def run_noop(self, params):
        return {'message': 'ok'}
"""

BASE = {'id': 'demo-x', 'name': 'X', 'version': '1.0.0', 'uses': ['documents']}


@pytest.fixture
def thing(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    spec = _load(write_plugin(tmp_path, "docthing", YAML, PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    spec.module.CALLS.clear()
    yield registry, spec
    registry.specs.pop(spec.id, None)


def ctx(registry, spec):
    from floorbit.plugins.base import Context
    return Context(spec, registry)


# ── the manifest ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("schema", [0, -1, "2", 2.5, True, 10_001])
def test_a_bad_schema_is_refused(schema):
    assert "schema: a whole number" in validate({**BASE, "schema": schema})


def test_a_schema_needs_data_to_move():
    assert "keeps no data" in validate({**BASE, "uses": ["widgets"], "schema": 1})
    assert validate({**BASE, "uses": ["storage"], "schema": 1}) == ""


def test_schema_and_migrate_come_together(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    no_migrate = _load(write_plugin(tmp_path / "a", "docthing", YAML, "from floorbit.plugins.base import Plugin\n"),
                       "development", registry.version)
    assert "has no migrate(from_schema, store)" in no_migrate.error
    no_schema = _load(write_plugin(tmp_path / "b", "docthing", YAML.replace("schema: 2\n", ""), PY),
                      "development", registry.version)
    assert "migrate() needs schema:" in no_schema.error


# ── documents ───────────────────────────────────────────────────────────────────────────────

def test_put_get_list_and_delete(thing):
    registry, spec = thing
    registry._update(spec.id, schema=2)          # nothing to migrate here
    notes = ctx(registry, spec).docs("notes")
    notes.put("seat A-1", {"text": "cable loose", "tags": ["power"]})
    notes.put("seat A-2", {"text": "ok"})
    assert notes.ids() == ["seat A-1", "seat A-2"]
    got = notes.get("seat A-1")
    got["text"] = "changed"                     # a copy: the stored one stays
    assert notes.get("seat A-1")["text"] == "cable loose"
    assert notes.get("nope", {}) == {}
    assert documents.collections(spec.id) == ["notes"]
    assert notes.delete("seat A-1") and not notes.delete("seat A-1")
    assert notes.delete("seat A-2")
    assert documents.collections(spec.id) == []   # the last one gone: no empty collection left


@pytest.mark.parametrize("name", ["../x", "Notes", "", "a" * 41, "x/y", None])
def test_a_collection_is_never_a_path(thing, name):
    registry, spec = thing
    with pytest.raises(PluginError, match="collection name"):
        ctx(registry, spec).docs(name)


@pytest.mark.parametrize("doc_id", ["", "x" * 129, "a\nb", 5, None])
def test_bad_document_ids_are_refused(thing, doc_id):
    registry, spec = thing
    with pytest.raises(PluginError, match="document id"):
        ctx(registry, spec).docs("notes").put(doc_id, {})


@pytest.mark.parametrize("doc", [{"x": float("nan")}, {"x": {1, 2}}, object()])
def test_only_plain_json_is_kept(thing, doc):
    registry, spec = thing
    with pytest.raises(PluginError, match="plain JSON"):
        ctx(registry, spec).docs("notes").put("a", doc)


def test_the_limits_hold(thing, monkeypatch):
    registry, spec = thing
    notes = ctx(registry, spec).docs("notes")
    with pytest.raises(PluginError, match="256 KB"):
        notes.put("big", {"x": "y" * (256 * 1024)})
    monkeypatch.setattr(documents, "PLUGIN_MAX_BYTES", 1000)
    notes.put("a", {"x": "y" * 400})
    ctx(registry, spec).docs("other").put("b", {"x": "y" * 400})
    with pytest.raises(PluginError, match="limited to"):
        notes.put("c", {"x": "y" * 400})
    notes.put("a", {"x": "y" * 10})               # replacing one counts its new size only
    monkeypatch.setattr(documents, "MAX_COLLECTIONS", 2)
    with pytest.raises(PluginError, match="at most 2 collections"):
        ctx(registry, spec).docs("third").put("a", {})


def test_documents_need_the_area(thing):
    registry, spec = thing
    spec.manifest["uses"] = ["storage", "actions"]
    try:
        with pytest.raises(PluginError, match="without listing it under uses"):
            ctx(registry, spec).docs("notes")
    finally:
        spec.manifest["uses"] = ["documents", "storage", "actions"]


def test_writes_at_once_all_land(thing):
    registry, spec = thing
    notes = ctx(registry, spec).docs("notes")
    threads = [threading.Thread(target=notes.put, args=(f"d{i}", {"i": i})) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(notes.ids()) == 20


@pytest.mark.parametrize("change", ["put", "delete"])
def test_a_write_from_another_pod_in_between_is_kept(thing, monkeypatch, change):
    """The per-plugin lock only holds inside one process: with two pods the store's merge must keep
    the other pod's document, not write back the copy read before it."""
    registry, spec = thing
    notes = ctx(registry, spec).docs("notes")
    notes.put("mine", {"n": 1})
    path = documents._path(spec.id, "notes")
    real = documents._read

    def read_then_other_pod_writes(plugin_id, name):
        data = real(plugin_id, name)
        store.write_json(path, {**store.read_json(path, {}), "theirs": {"pod": 2}})
        return data

    monkeypatch.setattr(documents, "_read", read_then_other_pod_writes)
    if change == "put":
        notes.put("new", {"n": 2})
    else:
        notes.delete("mine")
    monkeypatch.setattr(documents, "_read", real)
    assert "theirs" in notes.ids()
    assert ("new" in notes.ids()) == (change == "put") and ("mine" in notes.ids()) == (change == "put")


def test_each_tenant_has_its_own(thing):
    registry, spec = thing
    ctx(registry, spec).docs("notes").put("a", {"t": "one"})
    with store.using(tenant="tenants/other"):
        assert ctx(registry, spec).docs("notes").ids() == []
        ctx(registry, spec).docs("notes").put("a", {"t": "two"})
    assert ctx(registry, spec).docs("notes").get("a") == {"t": "one"}


# ── migrations ──────────────────────────────────────────────────────────────────────────────

def test_the_first_call_moves_the_data_once(thing):
    registry, spec = thing
    ctx(registry, spec).docs("notes").put("a", {"old": "from 1"})
    registry._update(spec.id, schema=1)
    assert registry.call(spec, "run_noop", {}) == {"message": "ok"}
    assert spec.module.CALLS == [1]
    assert ctx(registry, spec).docs("notes").get("a") == {"text": "from 1", "v": 2}
    assert registry.schema_of(spec.id) == 2 and registry.state_of(spec.id)["migrated_from"] == 1
    registry.call(spec, "run_noop", {})
    assert spec.module.CALLS == [1]                # not again
    assert "moved its data from schema 1 to 2" in [e["line"] for e in registry.logs.get(spec.id)]


def test_a_new_install_starts_at_zero(thing):
    registry, spec = thing
    registry.call(spec, "run_noop", {})
    assert spec.module.CALLS == [0] and registry.schema_of(spec.id) == 2


def test_a_failed_migration_stops_the_plugin_until_it_works(thing, monkeypatch):
    registry, spec = thing
    spec.module.FAIL.append(1)
    try:
        with pytest.raises(PluginError, match="could not move its data from schema 0 to 2"):
            registry.call(spec, "run_noop", {})
        with pytest.raises(PluginError, match="could not move"):
            registry.call(spec, "run_noop", {})
        assert spec.module.CALLS == [0]            # not tried again at once
        assert registry.schema_of(spec.id) == 0
    finally:
        spec.module.FAIL.clear()
    monkeypatch.setattr("floorbit.plugins.MIGRATE_RETRY", 0)
    assert registry.call(spec, "run_noop", {}) == {"message": "ok"}
    assert spec.module.CALLS == [0, 0] and registry.schema_of(spec.id) == 2


def test_a_migration_that_hangs_gives_up(thing, monkeypatch):
    registry, spec = thing
    monkeypatch.setattr("floorbit.plugins.MIGRATE_SECONDS", 0.2)
    spec.module.SLEEP.append(1)
    try:
        started = time.monotonic()
        with pytest.raises(PluginError, match="did not answer"):
            registry.call(spec, "run_noop", {})
        assert time.monotonic() - started < 1
        assert registry.schema_of(spec.id) == 0
    finally:
        spec.module.SLEEP.clear()
        time.sleep(1)                              # let the hung thread finish before the next test


def test_data_from_a_newer_version_is_never_handed_over(thing):
    registry, spec = thing
    registry._update(spec.id, schema=3)
    with pytest.raises(PluginError, match="data here is at schema 3"):
        registry.call(spec, "run_noop", {})
    assert spec.module.CALLS == []


def test_two_requests_migrate_once(thing):
    registry, spec = thing
    spec.module.SLEEP.append(0.3)
    try:
        threads = [threading.Thread(target=registry.call, args=(spec, "run_noop", {})) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        spec.module.SLEEP.clear()
    assert spec.module.CALLS == [0]


def test_the_plugin_list_shows_the_schema(client, thing):
    registry, spec = thing
    registry._update(spec.id, schema=1)
    row = next(p for p in client.get("/api/settings/plugins").get_json()["plugins"] if p["id"] == "docthing")
    assert (row["schema"], row["data_schema"]) == (2, 1)
