"""Which build runs here: floorbit/build_info.py and GET /api/version (the page footer)."""
import pytest

from floorbit import build_info
from tests.test_rbac import sign_in_as

SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(autouse=True)
def _fresh():
    build_info.info.cache_clear()
    yield
    build_info.info.cache_clear()


def test_image_values_win(monkeypatch):
    monkeypatch.setenv("FLOORBIT_COMMIT", SHA.upper())
    monkeypatch.setenv("FLOORBIT_BUILT", "2026-11-19T07:30:00Z")
    monkeypatch.setenv("FLOORBIT_RELEASE", "v1.2.0")
    monkeypatch.setenv("FLOORBIT_SOURCE", "https://github.com/example/floorbit/")
    info = build_info.info()
    assert info["commit"] == SHA and info["release"] == "1.2.0" and not info["dev"]
    assert info["built"] == 1795073400
    assert info["source"] == "https://github.com/example/floorbit"


def test_dev_checkout_asks_git(monkeypatch):
    for name in ("FLOORBIT_COMMIT", "FLOORBIT_BUILT", "FLOORBIT_RELEASE", "FLOORBIT_SOURCE"):
        monkeypatch.delenv(name, raising=False)
    answers = {("rev-parse", "HEAD"): SHA, ("show", "-s", "--format=%ct", "HEAD"): "1795073400"}
    monkeypatch.setattr(build_info, "_git", lambda *args: answers.get(args, ""))
    info = build_info.info()
    assert info["dev"] and info["commit"] == SHA and info["built"] == 1795073400 and info["release"] is None
    assert info["source"] == build_info.DEFAULT_SOURCE


def test_garbage_is_dropped(monkeypatch):
    monkeypatch.setenv("FLOORBIT_COMMIT", "<script>")
    monkeypatch.setenv("FLOORBIT_BUILT", "yesterday")
    monkeypatch.setenv("FLOORBIT_RELEASE", "latest; rm -rf")
    monkeypatch.setenv("FLOORBIT_SOURCE", "javascript:alert(1)")
    info = build_info.info()
    assert info["commit"] is None and info["built"] is None and info["release"] is None
    assert info["source"] == build_info.DEFAULT_SOURCE


def test_api_version_has_the_build_and_agents_only_for_admins(app_module, client, anon_client, monkeypatch):
    monkeypatch.setenv("FLOORBIT_COMMIT", SHA)
    body = client.get("/api/version").get_json()
    assert body["api"] == 1 and body["app"] and body["commit"] == SHA and body["agents"] == []
    assert "agents" not in anon_client.get("/api/version").get_json()
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert "agents" not in viewer.get("/api/version").get_json()
