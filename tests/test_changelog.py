"""Changelog fragments (scripts/changelog.py): parsing and merging into [Unreleased]."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'changelog', Path(__file__).resolve().parent.parent / 'scripts' / 'changelog.py')
changelog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changelog)

BASE = """# Changelog

## [Unreleased]

### Added

- Old entry.

## [1.0.0] - 2026-01-01

### Added

- First release.
"""


def test_merge_keeps_order_and_old_entries():
    merged = {'Fixed': ['- A fix.'], 'Added': ['- New thing,\n  over two lines.']}
    out = changelog.merge_into_unreleased(BASE, merged)
    unreleased = out[out.index('## [Unreleased]'):out.index('## [1.0.0]')]
    assert unreleased.index('### Added') < unreleased.index('### Fixed')
    assert '- Old entry.\n- New thing,\n  over two lines.' in unreleased
    assert out.endswith('- First release.\n')


def test_merge_into_empty_unreleased():
    text = BASE.replace('### Added\n\n- Old entry.\n\n', '')
    out = changelog.merge_into_unreleased(text, {'Changed': ['- Moved.']})
    assert '## [Unreleased]\n\n### Changed\n\n- Moved.\n\n## [1.0.0]' in out


@pytest.mark.parametrize('text', ['### Improved\n\n- x', '- no heading', '### Added\n\nloose text', '### Added\n'])
def test_bad_fragments_are_refused(text):
    with pytest.raises(ValueError):
        changelog.parse(text, 'x.md')


def test_repo_fragments_parse():
    changelog.collected()
