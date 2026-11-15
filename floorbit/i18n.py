"""German for the server's messages (issue #467).

The API answers errors in English (``{"error": "No such hall"}``). When the request asks for German
(the React app sends ``Accept-Language`` with the language picked in the sidebar), ``translate``
swaps the text for the one in ``locales/de-CH.json``. Messages built with values (``f"No such
block {name}"``) are written there with ``{}`` where the value goes; the German may put the
values in another order with ``{1}``, ``{2}``.

Standard German (``de``: Germany, Austria) is made from the Swiss texts, like in the React app
(frontend/src/i18n/germany.ts): only "ss" becomes "ß" in the words that need it.

``tests/test_i18n_server.py`` checks that every message in the code has a German text, so a new
message without one fails CI. ``locales/untranslated.txt`` lists the ones still waiting.
"""
import json
import os
import re
from functools import lru_cache

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locales')
_HOLE = re.compile(r'\{(\d*)\}')
_WORD = r'[^A-Za-zÄÖÜäöü]'

# The same words as frontend/src/i18n/germany.ts.
_SHARP_S = [
    (re.compile(rf'(^|{_WORD})([Gg])ross'), r'\1\2roß'),
    (re.compile(r'([Gg])rösse'), r'\1röße'),
    (re.compile(r'([Ss])chliess'), r'\1chließ'),
    (re.compile(r'([Dd])raussen'), r'\1raußen'),
    (re.compile(rf'(^|{_WORD})([Aa])ussen'), r'\1\2ußen'),
    (re.compile(rf'(^|{_WORD})([Aa])usser'), r'\1\2ußer'),
    (re.compile(rf'(^|{_WORD})([Ww])eiss(t?)(?![A-Za-zäöü])'), r'\1\2eiß\3'),
    (re.compile(r'([Ss])trasse'), r'\1traße'),
    (re.compile(rf'(^|{_WORD})([Ff])uss(?![A-Za-zäöü])'), r'\1\2uß'),
    (re.compile(r'([Gg])emäss'), r'\1emäß'),
    (re.compile(r'([Mm])ässig'), r'\1äßig'),
    (re.compile(r'([Hh])eiss'), r'\1eiß'),
    (re.compile(r'([Ss])pass(?![A-Za-zäöü])'), r'\1paß'),
    (re.compile(r'([Gg])russ'), r'\1ruß'),
    (re.compile(rf'(^|{_WORD})([Bb])loss(?![A-Za-zäöü])'), r'\1\2loß'),
]


def to_germany(text):
    for pattern, repl in _SHARP_S:
        text = pattern.sub(repl, text)
    return text


@lru_cache(maxsize=1)
def catalog():
    """(exact texts, [(pattern, German)] for texts with values)."""
    with open(os.path.join(HERE, 'de-CH.json'), encoding='utf-8') as f:
        texts = json.load(f)
    exact, patterns = {}, []
    for english, german in texts.items():
        if english.startswith('//'):
            continue
        if '{}' in english:
            parts = [re.escape(p) for p in english.split('{}')]
            patterns.append((re.compile('^' + '(.+?)'.join(parts) + '$', re.S), german))
        else:
            exact[english] = german
    return exact, patterns


def _fill(german, values):
    counter = iter(range(len(values)))

    def hole(m):
        i = int(m.group(1)) - 1 if m.group(1) else next(counter, 0)
        return values[i] if 0 <= i < len(values) else m.group(0)
    return _HOLE.sub(hole, german)


def translate(text, lang):
    """``text`` in ``lang`` ('de-CH', 'de', or anything else for English as it is)."""
    if not isinstance(text, str) or not lang or not lang.lower().startswith('de'):
        return text
    exact, patterns = catalog()
    german = exact.get(text)
    if german is None:
        for pattern, target in patterns:
            m = pattern.match(text)
            if m:
                german = _fill(target, m.groups())
                break
    if german is None:
        return text
    return german if lang.lower() in ('de-ch', 'de-li') else to_germany(german)


def language(accept):
    """The language to answer in from an Accept-Language header: 'de-CH', 'de' or 'en'."""
    for part in (accept or '').split(','):
        code = part.split(';')[0].strip().lower()
        if code in ('de', 'de-ch', 'de-li'):
            return 'de-CH'
        if code.startswith('de'):
            return 'de'
        if code.startswith('en'):
            return 'en'
    return 'en'


def init_app(app):
    """German error texts for German requests, at one place instead of at every ``jsonify``."""
    from flask import request

    @app.after_request
    def german_errors(response):
        if response.status_code < 400 or not response.is_json or response.direct_passthrough:
            return response
        lang = language(request.headers.get('Accept-Language'))
        if lang == 'en':
            return response
        data = response.get_json(silent=True)
        if isinstance(data, dict) and isinstance(data.get('error'), str):
            german = translate(data['error'], lang)
            if german != data['error']:
                data['error'] = german
                response.set_data(json.dumps(data, ensure_ascii=False))
        return response
