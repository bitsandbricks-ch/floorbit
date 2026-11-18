"""A plugin's icon: a name from Floorbit's own icon sets, never a file the plugin ships."""
import re
from pathlib import Path

import pytest
from test_marketplace import market  # noqa: F401  (fixture)

from floorbit import marketplace
from floorbit.plugins import plugin_icons, validate

ROOT = Path(__file__).resolve().parent.parent
BASE = {'id': 'demo-x', 'name': 'X', 'version': '1.0.0', 'uses': ['settings']}


@pytest.mark.parametrize('icon', ['shield', 'router', 'power-board'])
def test_a_known_icon_loads(icon):
    assert validate({**BASE, 'icon': icon}) == ''


@pytest.mark.parametrize('icon', ['nope', '', 'icon.svg', '<svg/>', ['shield'], 'https://example.com/x.png'])
def test_anything_else_is_refused(icon):
    assert validate({**BASE, 'icon': icon}).startswith('icon: one of')


def test_the_page_draws_every_name_floorbit_accepts():
    sources = (ROOT / 'frontend/src/nav/sections.ts').read_text() + (
        ROOT / 'frontend/src/pages/inventory/icons.tsx').read_text()
    drawn = set(re.findall(r"""^\s*'?([a-z][a-z-]*)'?: Icon\w+""", sources, re.M)) | set(
        re.findall(r"""[{,]\s*'?([a-z][a-z-]*)'?: Icon\w+""", sources))
    assert set(plugin_icons()) <= drawn


def test_every_builtin_plugin_has_an_icon(client):
    plugins = client.get('/api/settings/plugins').get_json()['plugins']
    assert plugins and all(p['icon'] in plugin_icons() for p in plugins)


@pytest.mark.parametrize('icon, shown', [('shield', 'shield'), ('evil.svg', ''), ('constructor', '')])
def test_the_marketplace_shows_only_icons_floorbit_knows(market, icon, shown):  # noqa: F811
    market.publish('hallthing', '1.0.0', icon=icon)
    hall = next(p for p in marketplace.catalog(market.registry)['plugins'] if p['id'] == 'hallthing')
    assert hall['icon'] == shown
