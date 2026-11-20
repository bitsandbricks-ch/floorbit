"""German for the server's messages (floorbit/i18n.py, issue #467).

Every message the code can send to a person (``{'error': ...}`` and ``raise SomethingError(...)``)
needs a German text in floorbit/locales/de-CH/<area>.json (or the older floorbit/locales/de-CH.json).
The ones still waiting are listed in floorbit/locales/untranslated.txt: that list may only get
shorter, so a new message without German fails here.
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
    return {k: v for k, v in i18n.load_texts('de-CH.json').items() if not k.startswith('//')}


def test_every_message_has_german_or_is_listed_as_waiting():
    have, todo = german(), waiting()
    missing = {text: where for text, where in messages_in_code().items() if text not in have and text not in todo}
    assert not missing, ('These messages need a German text in floorbit/locales/de-CH/<area>.json:\n'
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


@pytest.mark.parametrize('english, german', [
    ('Serves 1 range, 22 seats', 'Bedient 1 Bereich, 22 Plätze'),
    ('Serves 3 ranges, 1 seat', 'Bedient 3 Bereiche, 1 Platz'),
    ('2 ranges failed over', '2 Bereiche auf Backup umgeschaltet'),
    ('18/20 players on de_example', '18/20 Spieler auf de_example'),
    ('18/20 players', '18/20 Spieler'),
    ('The cache disk is 95 % full.', 'Die Cache-Disk ist zu 95 % voll.'),
    ('850 / 1000 Mbit/s in', '850 / 1000 Mbit/s eingehend'),
    ('DHCP players: needs a look', 'DHCP players: braucht einen Blick'),       # not the catch-all "{}: {}"
    ('Fiber multi-mode, 10G planned', 'Glasfaser Multimode, 10G geplant'),
    ('Feeds 12 seats', 'Speist 12 Plätze'),
    ('Seat A-2 is online without a check-in', 'Platz A-2 ist online ohne Check-in'),
    ('sw-a-01 Gi1/0/2 (seat A-2)', 'sw-a-01 Gi1/0/2 (Platz A-2)'),
    ('Loop detected (3 lines)', 'Schleife erkannt (3 Zeilen)'),
])
def test_health_tiles_built_in_speak_german(english, german):
    assert i18n.translate(english, 'de-CH') == german


def test_stored_status_messages_follow_the_page_language():
    rows = {'servers': [{'name': 'CS2 #1', 'error': 'No answer to the server query.'}, {'name': 'up', 'error': None}]}
    german = i18n.translate_fields(rows, 'de-CH')
    assert german['servers'][0] == {'name': 'CS2 #1', 'error': 'Keine Antwort auf die Serverabfrage.'}
    assert german['servers'][1]['error'] is None
    assert i18n.translate_fields(rows, 'en') is rows


def test_errors_inside_a_working_answer_are_german_too(client):
    """A status answer that worked can name a part that failed (the syslog's status.error)."""
    from floorbit import i18n
    app = client.application
    english = ('Syslog comes in through the local agent (the plugin "Syslog from the hall"); '
               'this server does not listen itself.')
    with app.test_request_context(headers={'Accept-Language': 'de-CH'}):
        body = {'lines': [], 'status': {'error': english, 'stores': [{'id': 'x', 'error': None}]}, 'note': english}
        assert i18n.german_nested(body, 'de-CH') is True
        assert body['status']['error'].startswith('Syslog kommt über den lokalen Agenten')
        assert body['note'] == english   # only error fields
        assert i18n.german_nested({'error': 'not a known text'}, 'de-CH') is False


@pytest.mark.parametrize('name', ['de-CH.json', 'log.de-CH.json', 'discord.de-CH.json'])
def test_a_text_is_in_one_file_only(name):
    # A text twice (in one file or two) would make the German depend on which one loads last.
    seen, twice = {}, []
    for path in i18n.catalog_paths(name):
        with open(path, encoding='utf-8') as f:
            pairs = json.load(f, object_pairs_hook=lambda p: p)
        assert isinstance(pairs, list), f'{path} must be one JSON object {{"English": "German"}}'
        for english, _german in pairs:
            if english.startswith('//'):
                continue
            if english in seen:
                twice.append(f'  {english!r}: {seen[english]} and {os.path.relpath(path, LOCALES)}')
            seen[english] = os.path.relpath(path, LOCALES)
    assert not twice, 'These texts are there twice, keep one:\n' + '\n'.join(twice)


def test_the_area_files_are_loaded(tmp_path, monkeypatch):
    (tmp_path / 'de-CH.json').write_text('{"Old text": "Alter Text"}', encoding='utf-8')
    (tmp_path / 'de-CH').mkdir()
    (tmp_path / 'de-CH' / 'cables.json').write_text('{"No such rack {}": "Kein Rack {}"}', encoding='utf-8')
    (tmp_path / 'de-CH' / 'README.md').write_text('not a catalog', encoding='utf-8')
    monkeypatch.setattr(i18n, 'HERE', str(tmp_path))
    i18n.catalog.cache_clear()
    try:
        assert i18n.translate('Old text', 'de-CH', ('de-CH.json',)) == 'Alter Text'
        assert i18n.translate('No such rack r1', 'de-CH', ('de-CH.json',)) == 'Kein Rack r1'
    finally:
        i18n.catalog.cache_clear()
