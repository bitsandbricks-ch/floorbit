"""docs/plugin-spec.md is the contract; these keep the loader and the page from drifting apart."""
import re
from pathlib import Path

import pytest

from floorbit.plugins import AREAS, MANIFEST_NEXT, validate
from floorbit.plugins.bundles import BundleError, file_hashes

SPEC = Path(__file__).resolve().parent.parent / 'docs' / 'plugin-spec.md'
BASE = {'id': 'demo-x', 'name': 'X', 'version': '1.0.0', 'uses': ['settings']}


def test_an_unknown_manifest_key_is_refused():
    assert 'unknown key(s) setings' in validate({**BASE, 'setings': []})


def test_keys_the_spec_marks_next_are_refused_until_built():
    # Empty once everything in the spec ships; the check stays for the next key it lists.
    for key in MANIFEST_NEXT:
        assert 'not supported by this Floorbit yet' in validate({**BASE, key: 'x'})


def test_the_known_keys_still_load():
    assert validate({**BASE, 'author': 'Mike', 'homepage': 'https://example.com', 'license': 'MIT',
                     'description': 'x', 'floorbit': '>=0.1'}) == ''


@pytest.mark.parametrize('name', ['static/app.js', 'ui.js', 'page.html', 'style.css', 'native.so',
                                  'templates/x.txt', 'lib.whl'])
def test_a_bundle_never_carries_browser_or_native_code(tmp_path, name):
    (tmp_path / 'plugin.yaml').write_text('id: x\n')
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('x')
    with pytest.raises(BundleError, match='no browser or native code'):
        file_hashes(tmp_path)


def test_python_yaml_markdown_and_locales_are_fine(tmp_path):
    for name in ('plugin.yaml', 'plugin.py', 'agent.py', 'logs.py', 'README.md', 'locales/de-CH.json'):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text('x')
    assert len(file_hashes(tmp_path)) == 6


def test_every_data_area_is_in_the_spec():
    text = SPEC.read_text(encoding='utf-8')
    listed = set(re.findall(r'^\| `([a-z_]+)` \|', text, re.M))
    data_areas = set(AREAS) - {'settings', 'actions', 'widgets', 'endpoints', 'hooks', 'http', 'storage',
                               'documents', 'context_menu', 'agent', 'panels', 'layers', 'pages'}
    assert data_areas <= listed, f'docs/plugin-spec.md misses {sorted(data_areas - listed)}'


def test_every_builtin_plugin_fits_the_spec():
    from floorbit.plugins import BUILTIN_DIR, _load
    for folder in sorted(p for p in BUILTIN_DIR.iterdir() if (p / 'plugin.yaml').is_file()):
        spec = _load(folder, 'builtin', '99.0')
        assert not spec.error or 'needs Floorbit' in spec.error, f'{folder.name}: {spec.error}'
        file_hashes(folder)


@pytest.mark.parametrize('lang', ['en', 'de-CH'])
def test_the_marketplace_names_every_area(lang):
    import json
    texts = json.loads((SPEC.parent.parent / 'frontend' / 'src' / 'i18n' / lang / 'marketplace.json').read_text())
    missing = sorted(set(AREAS) - set(texts['area']))
    assert not missing, f'marketplace.json ({lang}) has no area.{missing}'
