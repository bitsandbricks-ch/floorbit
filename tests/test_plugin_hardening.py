"""Load, faults and limits of the plugin system and the Marketplace (docs/plugin-spec.md, Limits)."""
import threading
import time

import pytest
import requests
from test_plugins import GOOD_PY, GOOD_YAML, turn_on, write_plugin

from floorbit import marketplace, plugins
from floorbit.plugins import PluginError, _load

SLOW_YAML = """
id: slowpoke
name: Slowpoke
version: "1.0"
uses: [widgets, endpoints, actions, hooks]
actions:
  - {id: note, role: editor}
widgets:
  - {id: tile}
endpoints:
  - {id: data}
hooks:
  - {events: [change], action: note}
"""

SLOW_PY = """
import threading
from floorbit.plugins.base import Plugin as Base

GATE = threading.Event()
SEEN = []

class Plugin(Base):
    def run_note(self, params):
        GATE.wait(5)
        SEEN.append(params['event'])

    def widget_tile(self):
        GATE.wait(5)
        return {'type': 'stat', 'value': 1}

    def endpoint_data(self, args):
        GATE.wait(5)
        return {'ok': True}
"""


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


@pytest.fixture
def slow(tmp_path, registry):
    spec = _load(write_plugin(tmp_path, "slowpoke", SLOW_YAML, SLOW_PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    registry.set_enabled(spec.id, True)
    yield spec, spec.module
    spec.module.GATE.set()
    registry.set_enabled(spec.id, False)
    registry.specs.pop(spec.id, None)


def test_a_burst_of_changes_uses_a_few_threads_and_drops_the_oldest(registry, slow, monkeypatch):
    _spec, mod = slow
    monkeypatch.setattr(plugins, "HOOK_QUEUE", 20)
    dropped = registry.hooks_dropped
    before = threading.active_count()
    for i in range(500):
        registry.emit("change", {"n": i})
    assert threading.active_count() - before <= plugins.HOOK_WORKERS
    assert registry.hooks_dropped - dropped >= 500 - 20 - plugins.HOOK_WORKERS
    assert registry.hooks_waiting() <= 20
    mod.GATE.set()
    deadline = time.time() + 5
    while registry.hooks_waiting() and time.time() < deadline:
        time.sleep(0.02)
    assert registry.hooks_waiting() == 0
    assert any("dropped: too many waiting" in line["line"] for line in registry.logs.get("slowpoke"))


def test_a_hung_tile_answers_within_the_budget(client, registry, slow, monkeypatch):
    monkeypatch.setattr(plugins, "REQUEST_BUDGET", 0.2)
    started = time.time()
    res = client.get("/api/plugins/slowpoke/widgets/tile")
    assert time.time() - started < 2
    assert "did not answer" in res.get_json()["error"]


def test_a_stuck_plugin_cant_take_every_worker(registry, slow):
    spec, mod = slow
    for _ in range(plugins.CALLS_PER_PLUGIN):
        with pytest.raises(PluginError, match="did not answer"):
            registry.timed(spec, "endpoint_data", {}, timeout=0.05)
    with pytest.raises(PluginError, match="still busy"):
        registry.timed(spec, "endpoint_data", {}, timeout=0.05)
    mod.GATE.set()
    deadline = time.time() + 5
    while registry._busy.get(spec.id) and time.time() < deadline:
        time.sleep(0.02)
    assert registry.timed(spec, "endpoint_data", {}) == {"ok": True}


def test_a_timed_call_keeps_the_requests_context(client, registry, tmp_path, monkeypatch):
    monkeypatch.setattr(plugins, "HOOKS_INLINE", True)
    spec = _load(write_plugin(tmp_path, "sample", GOOD_YAML, GOOD_PY), "development", registry.version)
    registry.specs[spec.id] = spec
    registry._register_settings()
    try:
        turn_on(client)
        client.post("/api/plugins/sample/actions/wave", json={"times": 2})
        assert client.get("/api/plugins/sample/widgets/count").get_json()["value"] == 2
    finally:
        registry.specs.pop(spec.id, None)


def test_is_it_on_reads_the_state_once_per_burst(registry, slow, monkeypatch):
    from floorbit import store
    reads = []
    real = store.read_json
    monkeypatch.setattr(store, "read_json", lambda *a, **k: (reads.append(a[0]), real(*a, **k))[1])
    registry._cache = None
    for _ in range(50):
        registry.feeders("monitoring")
        registry.as_list()
    assert len(reads) <= 2


def test_turning_on_is_seen_at_once_by_the_same_instance(registry, slow):
    spec, _ = slow
    registry.set_enabled(spec.id, False)
    assert not registry.enabled(spec)
    registry.set_enabled(spec.id, True)
    assert registry.enabled(spec)


def test_adding_a_plugin_never_changes_the_dict_being_iterated(registry, tmp_path):
    folder = write_plugin(tmp_path, "sample", GOOD_YAML, GOOD_PY)
    before = registry.specs
    try:
        registry.add(folder, "community")
        assert "sample" not in before and "sample" in registry.specs
        registry.drop("sample")
        assert "sample" not in registry.specs
    finally:
        registry.specs = {k: v for k, v in registry.specs.items() if k != "sample"}


class Big:
    def __init__(self, size, length=None):
        self.size, self.status_code = size, 200
        self.headers = {} if length is None else {"Content-Length": str(length)}

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        sent = 0
        while sent < self.size:
            sent += n
            yield b"x" * n

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("answer", [Big(10 * 1024 * 1024), Big(10, length=10 * 1024 * 1024)])
def test_a_huge_index_is_refused_before_it_is_in_memory(monkeypatch, answer):
    monkeypatch.setattr(requests, "get", lambda *a, **k: answer)
    marketplace._cache.clear()
    with pytest.raises(marketplace.MarketError, match="too large"):
        marketplace.fetch_index({"url": "https://example.com/huge.json"}, force=True)


def test_sync_says_how_many_it_could_not_load(registry, monkeypatch):
    monkeypatch.setattr(marketplace, "installed", lambda: {"ghost": {"version": "1.0.0"}})
    monkeypatch.setattr(marketplace, "_offers", lambda force=False: ({}, []))
    assert marketplace.sync(registry) == 1


# ── plugins that try to break Floorbit ──────────────────────────────────────────────────

EXIT_YAML = """
id: quitter
name: Quitter
version: "1.0"
uses: [widgets, storage, actions]
actions:
  - {id: count, role: editor, params: [{key: key, type: string}]}
widgets:
  - {id: tile}
"""

EXIT_PY = """
import sys
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    def widget_tile(self):
        sys.exit(3)

    def run_count(self, params):
        self.ctx.set_state(params['key'], 1)
"""


def test_a_plugin_that_calls_sys_exit_does_not_end_the_worker(client, registry, tmp_path):
    spec = _load(write_plugin(tmp_path, "quitter", EXIT_YAML, EXIT_PY), "development", registry.version)
    registry.specs[spec.id] = spec
    try:
        registry.set_enabled(spec.id, True)
        res = client.get("/api/plugins/quitter/widgets/tile")
        assert res.status_code >= 400 and "SystemExit" in res.get_json()["error"]
    finally:
        registry.set_enabled(spec.id, False)
        registry.specs.pop(spec.id, None)


@pytest.mark.parametrize("code, error", [
    ("import sys\nsys.exit(1)\n", "SystemExit"),
    ("import time\ntime.sleep(5)\n", "did not finish loading"),
])
def test_a_plugin_that_exits_or_hangs_at_import_does_not_stop_floorbit(tmp_path, monkeypatch, code, error):
    monkeypatch.setattr(plugins, "IMPORT_TIMEOUT", 0.5)
    started = time.time()
    spec = _load(write_plugin(tmp_path, "badimport", 'id: badimport\nname: B\nuses: [settings]\n', code),
                 "development", "1.0")
    assert error in spec.error
    assert time.time() - started < 3


def test_a_huge_manifest_is_refused_unread(tmp_path):
    folder = write_plugin(tmp_path, "huge", "id: huge\nname: H\nuses: [settings]\n# " + "x" * 300_000 + "\n")
    assert "larger than" in _load(folder, "development", "1.0").error


def test_hooks_setting_different_keys_at_once_keep_both(registry, tmp_path):
    spec = _load(write_plugin(tmp_path, "quitter", EXIT_YAML, EXIT_PY), "development", registry.version)
    registry.specs[spec.id] = spec
    try:
        threads = [threading.Thread(target=registry.call, args=(spec, "run_count", {"key": f"k{i}"}))
                   for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        assert set(registry.state_of("quitter")) == {f"k{i}" for i in range(20)}
    finally:
        registry.specs.pop(spec.id, None)


def _signed_index(generated):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from floorbit.plugins import bundles
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    pub = {bundles.key_id(key.public_key()): key.public_key()}
    return bundles.sign_index({"name": "x", "generated": generated, "plugins": []}, pem), pub


class Doc:
    def __init__(self, doc):
        import json
        self.body, self.status_code, self.headers = json.dumps(doc).encode(), 200, {}

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        yield self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def source(monkeypatch):
    from floorbit.plugins import bundles
    url = "https://example.com/stale/index.json"
    answers = []

    def get(*a, **k):
        a = answers[0]
        if isinstance(a, Exception):
            raise a
        return Doc(a)
    monkeypatch.setattr(requests, "get", get)
    marketplace._cache.pop(url, None)
    marketplace._newest.pop(url, None)
    marketplace._stale.pop(url, None)
    new, pub = _signed_index("2026-11-17T22:00:00Z")
    monkeypatch.setattr(bundles, "pinned_keys", lambda *a: pub)
    return {"url": url}, answers, new, pub


def test_while_the_index_is_away_its_last_good_copy_is_used(source):
    src, answers, new, _pub = source
    answers[:] = [new]
    assert marketplace.fetch_index(src, force=True)["generated"] == new["generated"]
    answers[:] = [requests.ConnectionError("down")]
    assert marketplace.fetch_index(src, force=True)["generated"] == new["generated"]
    assert "showing the copy from" in marketplace._stale[src["url"]]


def test_an_older_signed_index_is_refused_as_a_replay(source, monkeypatch):
    src, answers, new, pub = source
    answers[:] = [new]
    marketplace.fetch_index(src, force=True)
    old, old_pub = _signed_index("2026-11-01T00:00:00Z")
    from floorbit.plugins import bundles
    monkeypatch.setattr(bundles, "pinned_keys", lambda *a: {**pub, **old_pub})
    marketplace._cache.pop(src["url"], None)     # no copy to fall back on: the refusal shows
    answers[:] = [old]
    with pytest.raises(marketplace.MarketError, match="older"):
        marketplace.fetch_index(src, force=True)
