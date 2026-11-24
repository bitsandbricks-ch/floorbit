"""Move the server's German out of the single files into one file per area (issue #1230).

    python scripts/split_locales.py

Takes every text in ``floorbit/locales/de-CH.json`` and ``log.de-CH.json``, finds the module whose
code holds it, and adds it to ``de-CH/<area>.json`` (``log.de-CH/<area>.json``); texts found in no
module go to ``shared.json``. Then it deletes the single files. A text already in an area file keeps
that file's German. Run it again after merging ``master`` into a branch that still added to a single
file (keep the branch's version of that file when git asks): it moves that branch's texts too.
"""
import ast
import glob
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = os.path.join(ROOT, 'floorbit', 'locales')
SINGLE = ('de-CH.json', 'log.de-CH.json')


def area_of(path):
    rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
    parts = rel[:-len('.py')].split('/')
    if parts[0] == 'auth':
        return 'auth'
    if parts[0] == 'floorbit' and len(parts) > 2 and parts[1] in ('blueprints', 'builtin_plugins'):
        return parts[2]
    if parts[0] == 'floorbit' and len(parts) > 2:
        return parts[1]
    name = parts[-1]
    return 'core' if name == '__init__' else name


def _shape(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(x.value if isinstance(x, ast.Constant) else '{}' for x in node.values)
    return None


def texts_in_code():
    """{text as written in a locale file: area} for every string in the Python code."""
    found = {}
    files = []
    for folder in ('floorbit', 'auth', 'integrations'):
        files += glob.glob(os.path.join(ROOT, folder, '**', '*.py'), recursive=True)
    for path in sorted(files):
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            text = _shape(node)
            if text and text.strip('{} '):
                found.setdefault(text, area_of(path))
                # '{} of {}'.format(...) and '%s' templates read as '{}' in the locale files.
                found.setdefault(re.sub(r'%[sd]|\{\w*\}', '{}', text), area_of(path))
    return found


def _read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _write(path, texts):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(texts, ensure_ascii=False, indent=1) + '\n')


def split(name, code):
    single = os.path.join(LOCALES, name)
    if not os.path.exists(single):
        return 0
    folder = os.path.join(LOCALES, name[:-len('.json')])
    os.makedirs(folder, exist_ok=True)
    existing = {}
    for path in glob.glob(os.path.join(folder, '*.json')):
        for english in _read(path):
            existing[english] = path
    areas = {}
    for english, german in _read(single).items():
        if english.startswith('//') or english in existing:
            continue
        areas.setdefault(code.get(english, 'shared'), {})[english] = german
    for area, texts in areas.items():
        path = os.path.join(folder, f'{area}.json')
        if subprocess.run(['git', 'check-ignore', '-q', path], cwd=ROOT).returncode == 0:
            # .gitignore leaves out state files such as plugins.json: a texts file must not match.
            path = os.path.join(folder, f'{area}_texts.json')
        merged = _read(path) if os.path.exists(path) else {}
        merged.update(texts)
        _write(path, dict(sorted(merged.items(), key=lambda kv: kv[0].lower())))
    os.remove(single)
    return sum(len(t) for t in areas.values())


def main():
    code = texts_in_code()
    for name in SINGLE:
        moved = split(name, code)
        print(f'{name}: moved {moved} texts')


if __name__ == '__main__':
    main()
