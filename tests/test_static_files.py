"""Static files: gzipped when the browser takes it, hashed build files cached for good (#1291)."""
import gzip

import pytest


@pytest.fixture
def asset(app_module, tmp_path, monkeypatch):
    folder = tmp_path / "static"
    (folder / "app" / "assets").mkdir(parents=True)
    (folder / "js").mkdir()
    body = b"console.log('floorbit');\n" * 400
    (folder / "app" / "assets" / "index-Ab12Cd34.js").write_bytes(body)
    (folder / "js" / "notify.js").write_bytes(body)
    monkeypatch.setattr(app_module.app, "static_folder", str(folder))
    return "/static/app/assets/index-Ab12Cd34.js", body


def test_a_hashed_build_file_is_gzipped_and_kept_for_a_year(client, asset):
    url, body = asset
    r = client.get(url, headers={"Accept-Encoding": "gzip, br"})
    assert r.status_code == 200
    assert r.headers["Content-Encoding"] == "gzip"
    assert gzip.decompress(r.data) == body
    assert len(r.data) < len(body) / 5
    assert "immutable" in r.headers["Cache-Control"]
    assert "Accept-Encoding" in r.headers["Vary"]
    assert r.headers["ETag"].startswith('W/')


def test_without_gzip_the_file_comes_as_is(client, asset):
    url, body = asset
    r = client.get(url, headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200 and "Content-Encoding" not in r.headers and r.data == body


def test_the_weak_tag_still_gets_a_304(client, asset):
    url, _ = asset
    tag = client.get(url, headers={"Accept-Encoding": "gzip"}).headers["ETag"]
    r = client.get(url, headers={"Accept-Encoding": "gzip", "If-None-Match": tag})
    assert r.status_code == 304


def test_other_static_files_are_asked_for_each_time(client, asset):
    r = client.get("/static/js/notify.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers["Content-Encoding"] == "gzip"
    assert "immutable" not in (r.headers.get("Cache-Control") or "")


def test_pages_and_api_answers_are_not_compressed(client):
    # They can hold a secret next to text an attacker chose (BREACH).
    r = client.get("/api/version", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in r.headers
