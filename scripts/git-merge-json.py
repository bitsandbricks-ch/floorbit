#!/usr/bin/env python3
"""A git merge driver for the translation files: merges them by key, not by line.

Two pull requests that each add texts to the same JSON file almost always touch neighbouring lines,
so a plain merge stops with a conflict although nothing really clashes. This driver first tries the
plain line merge; only when that conflicts does it merge the three versions key by key. A real
clash (both sides changed the same text differently) still stops as a conflict.

Set it up once per clone (``scripts/setup-git.sh`` does it):

    git config merge.json-texts.driver "python3 scripts/git-merge-json.py %O %A %B"

``.gitattributes`` says which files use it. Without the setup, and on GitHub, git falls back to the
plain line merge, so nothing changes there.
"""
import json
import subprocess
import sys


class Clash(Exception):
    pass


_MISSING = object()


def _insert_after(items, key, value, after):
    """``items`` (a list of pairs) with ``key`` put right after ``after`` (first when None; last
    when ``after`` is gone)."""
    if after is None:
        items.insert(0, (key, value))
        return
    for i, (k, _v) in enumerate(items):
        if k == after:
            items.insert(i + 1, (key, value))
            return
    items.append((key, value))


def merge(base, ours, theirs):
    if ours == theirs:
        return ours
    if base == ours:
        return theirs
    if base == theirs:
        return ours
    if not all(isinstance(x, dict) for x in (ours, theirs)):
        raise Clash()
    base = base if isinstance(base, dict) else {}
    items = list(ours.items())
    index = {k: i for i, (k, _v) in enumerate(items)}
    removed = set()
    previous = None
    for key, value in theirs.items():
        if key in ours:
            items[index[key]] = (key, merge(base.get(key, _MISSING), ours[key], value))
        elif key in base:
            # We removed it: fine if they left it as it was.
            if value != base[key]:
                raise Clash()
        else:
            _insert_after(items, key, value, previous)
            index = {k: i for i, (k, _v) in enumerate(items)}
        previous = key
    for key in base:
        if key not in theirs and key in ours:
            if ours[key] != base[key]:
                raise Clash()
            removed.add(key)
    return {k: v for k, v in items if k not in removed}


def _format_of(text, data):
    """The json.dumps arguments that write ``text`` the way it is, or None. Every line they write
    must be in the file already: only a doubled key may drop out, nothing gets laid out anew."""
    def lines(t):
        # The last entry has no comma; with a doubled key dropped, another one becomes the last.
        return {line.rstrip(',') for line in t.splitlines()}
    have = lines(text)
    for indent in (2, 1, 4):
        if lines(json.dumps(data, ensure_ascii=False, indent=indent)) <= have:
            return {'ensure_ascii': False, 'indent': indent}
    return None


def main(base_path, ours_path, theirs_path):
    plain = subprocess.run(['git', 'merge-file', '-p', '-L', 'ours', '-L', 'base', '-L', 'theirs',
                            ours_path, base_path, theirs_path], capture_output=True)
    if plain.returncode == 0:
        with open(ours_path, 'wb') as f:
            f.write(plain.stdout)
        return 0
    try:
        texts = []
        for path in (base_path, ours_path, theirs_path):
            with open(path, encoding='utf-8') as f:
                texts.append(f.read())
        base, ours, theirs = (json.loads(t) if t.strip() else {} for t in texts)
        fmt = _format_of(texts[1], ours)
        if fmt is None:
            raise Clash()
        result = json.dumps(merge(base, ours, theirs), **fmt) + '\n'
    except (Clash, ValueError):
        # Leave the usual conflict markers for a person to resolve.
        with open(ours_path, 'wb') as f:
            f.write(plain.stdout)
        return 1
    with open(ours_path, 'w', encoding='utf-8') as f:
        f.write(result)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
