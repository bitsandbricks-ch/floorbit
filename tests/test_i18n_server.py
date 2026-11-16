"""German for the server's messages (floorbit/i18n.py, issue #467).

Every message the code can send to a person (``{'error': ...}`` and ``raise SomethingError(...)``)
needs a German text in floorbit/locales/de-CH.json. The ones still waiting are listed in
floorbit/locales/untranslated.txt: that list may only get shorter, so a new message without German
fails here.
"""
import ast
import glob
import json
import os

import pytest

from floorbit import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = os.path.join(ROOT, 'floorbit', 'locales')
ERROR_ENDINGS = ('Error', 'Unavailable', 'Refused')


def _text(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(x.value if isinstance(x, ast.Constant) else '{}' for x in node.values)
    return None


def messages_in_code():
    found = {}
    files = []
    for folder in ('floorbit', 'auth', 'integrations'):
        files += glob.glob(os.path.join(ROOT, folder, '**', '*.py'), recursive=True)
    for path in sorted(files):
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            candidates = []
            if isinstance(node, ast.Dict):
                candidates = [v for k, v in zip(node.keys, node.values, strict=True)
                              if isinstance(k, ast.Constant) and k.value == 'error']
            elif (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args
                  and ast.unparse(node.exc.func).split('.')[-1].endswith(ERROR_ENDINGS)):
                candidates = [node.exc.args[0]]
            for value in candidates:
                text = _text(value)
                if text and text.strip('{} '):
                    found.setdefault(text, os.path.relpath(path, ROOT))
    return found


def waiting():
    with open(os.path.join(LOCALES, 'untranslated.txt'), encoding='utf-8') as f:
        return {json.loads(line) for line in f if line.strip() and not line.startswith('#')}


def german():
    with open(os.path.join(LOCALES, 'de-CH.json'), encoding='utf-8') as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith('//')}


def test_every_message_has_german_or_is_listed_as_waiting():
    have, todo = german(), waiting()
    missing = {text: where for text, where in messages_in_code().items() if text not in have and text not in todo}
    assert not missing, ('These messages need a German text in floorbit/locales/de-CH.json:\n'
                         + '\n'.join(f'  {where}: {text!r}' for text, where in sorted(missing.items())))


def test_the_waiting_list_only_shrinks():
    in_code, have = messages_in_code(), german()
    stale = sorted(t for t in waiting() if t not in in_code or t in have)
    assert not stale, ('Remove these lines from floorbit/locales/untranslated.txt (translated or gone):\n'
                       + '\n'.join(f'  {json.dumps(t, ensure_ascii=False)}' for t in stale))


def test_german_texts_keep_their_values_and_write_swiss():
    for english, text in german().items():
        assert 'ß' not in text, english
        holes = english.count('{}')
        assert text.count('{}') + sum(text.count(f'{{{i}}}') for i in range(1, holes + 1)) >= holes, english


@pytest.mark.parametrize('lang, expected', [
    ('de-CH', 'Diese Halle gibt es nicht'),
    ('de', 'Diese Halle gibt es nicht'),
    ('en', 'No such hall'),
])
def test_translate(lang, expected):
    assert i18n.translate('No such hall', lang) == expected


def test_values_are_carried_over_and_germany_gets_sharp_s():
    assert i18n.translate('The background is at most 8 MB', 'de-CH') == 'Der Hintergrund ist höchstens 8 MB gross'
    assert i18n.translate('The background is at most 8 MB', 'de') == 'Der Hintergrund ist höchstens 8 MB groß'
    assert i18n.translate('Something nobody wrote down', 'de-CH') == 'Something nobody wrote down'


@pytest.mark.parametrize('header, lang', [
    ('de-CH,de;q=0.9,en;q=0.8', 'de-CH'), ('de', 'de-CH'), ('de-DE,en', 'de'),
    ('en-GB,de', 'en'), ('fr-CH', 'en'), (None, 'en'),
])
def test_language_from_the_header(header, lang):
    assert i18n.language(header) == lang


def test_api_errors_come_in_the_asked_language(client):
    en = client.get('/api/halls/nope/background')
    de = client.get('/api/halls/nope/background', headers={'Accept-Language': 'de-CH'})
    assert en.status_code == de.status_code == 404
    assert i18n.translate(en.get_json()['error'], 'de-CH') == de.get_json()['error'] != en.get_json()['error']
