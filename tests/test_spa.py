"""The React pages: Flask renders templates/spa.html with the assets from Vite's manifest."""
import json

from floorbit import spa


def _manifest(tmp_path, monkeypatch, data):
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(data))
    monkeypatch.setattr(spa, '_manifest_path', lambda: str(path))


def test_page_loads_the_built_assets(client, app_module, tmp_path, monkeypatch):
    _manifest(tmp_path, monkeypatch, {
        'index.html': {'file': 'assets/index-abc.js', 'css': ['assets/index-abc.css'], 'imports': ['_shared.js']},
        '_shared.js': {'file': 'assets/shared.js', 'css': ['assets/shared.css']},
    })
    resp = client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert '<script type="module" src="/static/app/assets/index-abc.js">' in html
    assert '/static/app/assets/index-abc.css' in html and '/static/app/assets/shared.css' in html
    # The theme head comes first, so the preset applies before React paints.
    assert html.index('brand/tokens.css') < html.index('/static/app/assets/index-abc.css')


def test_without_a_build_the_page_says_how_to_make_one(client, app_module, monkeypatch):
    monkeypatch.setattr(spa, '_manifest_path', lambda: '/nonexistent/manifest.json')
    resp = client.get('/settings/plugins')
    assert resp.status_code == 503
    assert b'npm run build' in resp.data


def test_the_page_still_needs_sign_in(anon_client, app_module):
    assert anon_client.get('/dashboard').status_code == 302
