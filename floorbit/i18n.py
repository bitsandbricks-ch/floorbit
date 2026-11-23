"""German for the server's messages (issue #467).

The API answers errors in English (``{"error": "No such hall"}``). When the request asks for German
(the React app sends ``Accept-Language`` with the language picked in the sidebar), ``translate``
swaps the text for the one in ``locales/de-CH.json`` or a file in ``locales/de-CH/`` (one per area:
new texts go there, see ``catalog_paths``). Messages built with values (``f"No such
block {name}"``) are written there with ``{}`` where the value goes; the German may put the
values in another order with ``{1}``, ``{2}``.

Standard German (``de``: Germany, Austria) is made from the Swiss texts, like in the React app
(frontend/src/i18n/germany.ts): only "ss" becomes "ß" in the words that need it.

The audit log, event changelog and handover show their entries through ``log_text``, from
``locales/log.de-CH.json`` (``tests/test_i18n_log.py`` checks every audit action has German).

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


def catalog_paths(name):
    """The files that make up the catalog ``name``: ``locales/<name>`` and every ``*.json`` in the
    folder next to it (``de-CH.json`` -> ``de-CH/``), sorted. A pull request puts its texts in a file
    of its own area there, so parallel pull requests don't all add lines to the one big file."""
    paths = []
    single = os.path.join(HERE, name)
    if os.path.exists(single):
        paths.append(single)
    folder = os.path.join(HERE, name[:-len('.json')] if name.endswith('.json') else name)
    if os.path.isdir(folder):
        paths += sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.endswith('.json'))
    return paths


def load_texts(name):
    """``{English: German}`` of the catalog ``name`` (all its files, see ``catalog_paths``)."""
    texts = {}
    for path in catalog_paths(name):
        with open(path, encoding='utf-8') as f:
            texts.update(json.load(f))
    return texts


@lru_cache(maxsize=4)
def catalog(files=('de-CH.json',)):
    """(exact texts, [(pattern, German)] for texts with values), from ``files`` (later ones win)."""
    texts = {}
    for name in files:
        texts.update(load_texts(name))
    return compile_texts(texts)


def compile_texts(texts):
    """(exact, patterns) for ``{"English": "German"}``, as ``catalog`` builds them: also used for a
    plugin's own ``locales/de-CH.json`` (floorbit/plugins/__init__.py)."""
    exact, patterns = {}, []
    for english, german in texts.items():
        if english.startswith('//'):
            continue
        if '{}' in english:
            patterns.append((len(english) - 2 * english.count('{}'), _Pattern(english.split('{}')), german))
        else:
            exact[english] = german
    # The most specific text wins: "{}: needs a look" before "{}: {}", whatever order the file has.
    patterns.sort(key=lambda p: -p[0])
    return exact, [(rx, german) for _n, rx, german in patterns]


class _Pattern:
    """``"{} of {}"`` as literal parts with a hole of one or more characters between each two.

    A regex of lazy ``(.+?)`` groups gives the same answer, but takes polynomial time in the
    number of holes on a long text that doesn't match: with a plugin's own texts (or an error
    message with someone's input in it) one request could hang. Each part is looked for once,
    leftmost first; with nothing but "any text" between the parts that finds a match whenever
    there is one, and the same one the lazy regex finds."""

    __slots__ = ('parts',)

    def __init__(self, parts):
        self.parts = parts

    def match(self, text):
        parts = self.parts
        if not text.startswith(parts[0]) or not text.endswith(parts[-1]):
            return None
        pos, end = len(parts[0]), len(text) - len(parts[-1])
        groups = []
        for part in parts[1:-1]:
            at = text.find(part, pos + 1, end) if part else pos + 1
            if at < 0 or at >= end:
                return None
            groups.append(text[pos:at])
            pos = at + len(part)
        if end - pos < 1:
            return None
        groups.append(text[pos:end])
        return _Match(groups)


class _Match(tuple):
    def groups(self):
        return tuple(self)


def _fill(german, values):
    counter = iter(range(len(values)))

    def hole(m):
        i = int(m.group(1)) - 1 if m.group(1) else next(counter, 0)
        return values[i] if 0 <= i < len(values) else m.group(0)
    return _HOLE.sub(hole, german)


DISCORD = ('de-CH.json', 'discord.de-CH.json')


def translate(text, lang, files=('de-CH.json',)):
    """``text`` in ``lang`` ('de-CH', 'de', or anything else for English as it is)."""
    if not isinstance(text, str) or not lang or not lang.lower().startswith('de'):
        return text
    return translate_in(text, lang, catalog(files))


def translate_in(text, lang, compiled, fallback=True):
    """``text`` in ``lang`` from one compiled catalog. ``fallback``: English when it has no German;
    else None, so the caller can try another catalog."""
    if not isinstance(text, str) or not lang or not lang.lower().startswith('de'):
        return text
    exact, patterns = compiled
    german = exact.get(text)
    if german is None:
        for pattern, target in patterns:
            m = pattern.match(text)
            if m:
                german = _fill(target, m.groups())
                break
    if german is None:
        return text if fallback else None
    return german if lang.lower() in ('de-ch', 'de-li') else to_germany(german)


LOG = ('log.de-CH.json',)
_FIELDS = re.compile(r'^(.+) \(([^()]*)\)$', re.S)


def log_text(text, lang):
    """An audit action or changelog title in ``lang``, from ``locales/log.de-CH.json``. Unlike
    ``translate``, the values go through too ("Incident opened: No internet at the seat"), and a
    title with the changed fields after it ("Changed cable (label, route)") keeps them as they are."""
    if not isinstance(text, str) or not lang or not lang.lower().startswith('de'):
        return text
    german = _log_german(text)
    if german is None:
        return text
    return german if lang.lower() in ('de-ch', 'de-li') else to_germany(german)


def _log_german(text, depth=0):
    exact, patterns = catalog(LOG)
    if text in exact:
        return exact[text]
    if depth < 2:
        for pattern, target in patterns:
            m = pattern.match(text)
            if m:
                return _fill(target, [_log_german(v, depth + 1) or v for v in m.groups()])
    m = _FIELDS.match(text)
    if m:
        head = _log_german(m.group(1), depth)
        return f'{head} ({m.group(2)})' if head is not None else None
    return None


_TEXT_KEYS = ('content', 'title', 'description', 'name', 'value', 'text', 'label', 'placeholder')


def translate_payload(payload, lang):
    """A Discord message (embeds, fields, buttons) with its texts in ``lang``, line by line. Values
    that aren't Floorbit's own texts (switch names, the crew's notes) match nothing and stay."""
    if not lang or not lang.lower().startswith('de'):
        return payload

    def walk(value, key=None):
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key) for v in value]
        if isinstance(value, str) and key in _TEXT_KEYS:
            return '\n'.join(translate(line, lang, DISCORD) for line in value.split('\n'))
        return value
    return walk(payload)


def translate_fields(value, lang, keys=('error',)):
    """``value`` with the strings under ``keys`` in ``lang``, at any depth: status messages the
    pollers stored in English («No answer to the server query.») for a German page."""
    if not lang or not lang.lower().startswith('de'):
        return value
    if isinstance(value, dict):
        return {k: (translate(v, lang) if k in keys and isinstance(v, str) else translate_fields(v, lang, keys))
                for k, v in value.items()}
    if isinstance(value, list):
        return [translate_fields(v, lang, keys) for v in value]
    return value


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


NESTED_MAX_BYTES = 256 * 1024   # bigger answers (plan data, exports) aren't walked for errors


def _is_error_key(key):
    return key == 'error' or key.endswith('_error')


def german_nested(data, lang, depth=0):
    """Status answers carry errors deeper down (``status.error``, ``stores[].error``,
    ``query_error``): put each in ``lang``. Returns whether anything changed."""
    if depth > 4:
        return False
    changed = False
    items = data.items() if isinstance(data, dict) else enumerate(data) if isinstance(data, list) else ()
    for key, value in list(items)[:500]:
        if isinstance(value, str):
            if isinstance(key, str) and _is_error_key(key):
                german = translate(value, lang)
                if german != value:
                    data[key] = german
                    changed = True
        elif isinstance(value, (dict, list)):
            changed = german_nested(value, lang, depth + 1) or changed
    return changed


def init_app(app):
    """German error texts for German requests, at one place instead of at every ``jsonify``."""
    from flask import request

    @app.after_request
    def german_errors(response):
        if not response.is_json or response.direct_passthrough:
            return response
        lang = language(request.headers.get('Accept-Language'))
        if lang == 'en':
            return response
        if response.status_code < 400:
            # An answer that worked can still report a part that didn't (a status line, a plugin).
            if (response.content_length or 0) > NESTED_MAX_BYTES or b'error"' not in response.get_data():
                return response
            data = response.get_json(silent=True)
            if isinstance(data, (dict, list)) and german_nested(data, lang):
                response.set_data(json.dumps(data, ensure_ascii=False))
            return response
        data = response.get_json(silent=True)
        if isinstance(data, dict) and isinstance(data.get('error'), str):
            german = translate(data['error'], lang)
            if german != data['error']:
                data['error'] = german
                response.set_data(json.dumps(data, ensure_ascii=False))
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
