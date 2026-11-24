"""scripts/git-merge-json.py: translation files merge by key, so parallel pull requests that each
add texts don't conflict, while a real clash still does."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = os.path.join(ROOT, 'scripts', 'git-merge-json.py')


def _merge(tmp_path, base, ours, theirs, indent=1):
    paths = []
    for name, data in (('base', base), ('ours', ours), ('theirs', theirs)):
        path = tmp_path / f'{name}.json'
        path.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + '\n', encoding='utf-8')
        paths.append(str(path))
    done = subprocess.run([sys.executable, DRIVER, *paths], capture_output=True)
    return done.returncode, (tmp_path / 'ours.json').read_text(encoding='utf-8')


def test_both_sides_add_texts_at_the_same_place(tmp_path):
    base = {'A': 'a', 'Z': 'z'}
    ours = {'A': 'a', 'New from us': 'Neu von uns', 'Z': 'z'}
    theirs = {'A': 'a', 'New from them': 'Neu von ihnen', 'Z': 'z'}
    code, text = _merge(tmp_path, base, ours, theirs)
    assert code == 0
    assert json.loads(text) == {'A': 'a', 'New from them': 'Neu von ihnen', 'New from us': 'Neu von uns', 'Z': 'z'}
    assert text.startswith('{\n "A": "a",')   # written the way the file was: one space, real umlauts


def test_nested_texts_and_a_removal(tmp_path):
    base = {'title': 'Problems', 'count': {'down': '{{n}} down'}, 'old': 'gone soon'}
    ours = {'title': 'Problems', 'count': {'down': '{{n}} down', 'warn': '{{n}} to look at'}}
    theirs = {'title': 'Problems', 'count': {'down': '{{n}} down', 'muted': '{{n}} muted'}, 'old': 'gone soon',
              'intro': 'Everything wrong'}
    code, text = _merge(tmp_path, base, ours, theirs, indent=2)
    assert code == 0
    merged = json.loads(text)
    assert merged['count'] == {'down': '{{n}} down', 'muted': '{{n}} muted', 'warn': '{{n}} to look at'}
    assert 'old' not in merged and merged['intro'] == 'Everything wrong'


def test_the_same_text_changed_two_ways_is_still_a_conflict(tmp_path):
    base = {'intro': 'Everything wrong'}
    code, text = _merge(tmp_path, base, {'intro': 'Everything wrong now'}, {'intro': 'All that is wrong'})
    assert code != 0
    assert '<<<<<<<' in text and '>>>>>>>' in text


def test_a_clean_line_merge_is_kept_as_it_is(tmp_path):
    base = {'a': '1', 'b': '2', 'c': '3', 'd': '4', 'e': '5'}
    code, text = _merge(tmp_path, base, {**base, 'a': 'one'}, {**base, 'e': 'five'})
    assert code == 0 and json.loads(text) == {'a': 'one', 'b': '2', 'c': '3', 'd': '4', 'e': 'five'}
