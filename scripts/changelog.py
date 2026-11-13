"""Changelog fragments: one small file per pull request in changelog.d/, merged at release.

Every PR used to add its lines to CHANGELOG.md's [Unreleased] section, so any two open PRs
conflicted there. Now each PR adds changelog.d/<topic>.md instead, with the usual Keep a
Changelog headings:

    ### Added

    - Kiosk view at `/kiosk` ...

    python scripts/changelog.py check      validate the fragments (CI runs this)
    python scripts/changelog.py preview    print [Unreleased] as it would be after collect
    python scripts/changelog.py collect    merge them into CHANGELOG.md and delete them;
                                           run it on the release branch before `mason bump`
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS = ROOT / 'changelog.d'
CHANGELOG = ROOT / 'CHANGELOG.md'
# Keep a Changelog order.
KINDS = ['Added', 'Changed', 'Deprecated', 'Removed', 'Fixed', 'Security']
HEADING = re.compile(r'^### (.+?)\s*$')


def fragment_files():
    return sorted(p for p in FRAGMENTS.glob('*.md') if p.name != 'README.md')


def parse(text, source):
    """{kind: [entry, ...]} where an entry is a bullet with its continuation lines."""
    out, kind, entry = {}, None, None
    for n, line in enumerate(text.splitlines(), 1):
        m = HEADING.match(line)
        if m:
            kind = m.group(1)
            if kind not in KINDS:
                raise ValueError(f'{source}:{n}: unknown heading "### {kind}"; use one of {", ".join(KINDS)}')
            out.setdefault(kind, [])
            entry = None
        elif line.startswith('- '):
            if kind is None:
                raise ValueError(f'{source}:{n}: a "- " entry needs a "### Added/Changed/..." heading above it')
            entry = [line]
            out[kind].append(entry)
        elif line.strip() and entry is not None and line.startswith('  '):
            entry.append(line)
        elif line.strip():
            raise ValueError(f'{source}:{n}: expected "### Kind", "- entry" or an indented continuation')
    if not any(out.values()):
        raise ValueError(f'{source}: no entries')
    return {k: ['\n'.join(e) for e in v] for k, v in out.items()}


def collected():
    merged = {}
    for path in fragment_files():
        for kind, entries in parse(path.read_text(), path.relative_to(ROOT)).items():
            merged.setdefault(kind, []).extend(entries)
    return merged


def merge_into_unreleased(changelog, merged):
    """CHANGELOG.md text with the fragments added to [Unreleased], under their headings."""
    start = changelog.index('## [Unreleased]')
    nxt = changelog.find('\n## ', start + 1)
    end = len(changelog) if nxt == -1 else nxt + 1
    current = parse(changelog[start:end].split('\n', 1)[1], 'CHANGELOG.md [Unreleased]') \
        if re.search(r'(?m)^- ', changelog[start:end]) else {}
    for kind, entries in merged.items():
        current.setdefault(kind, []).extend(entries)
    body = ''.join(f'### {k}\n\n' + '\n'.join(current[k]) + '\n\n' for k in KINDS if current.get(k))
    return changelog[:start] + '## [Unreleased]\n\n' + body + changelog[end:].lstrip('\n')


def main(argv):
    cmd = argv[1] if len(argv) > 1 else 'check'
    try:
        merged = collected()
    except ValueError as exc:
        sys.exit(f'changelog.d: {exc}')
    if cmd == 'check':
        print(f'{len(fragment_files())} fragment(s) OK')
    elif cmd == 'preview':
        text = merge_into_unreleased(CHANGELOG.read_text(), merged)
        start = text.index('## [Unreleased]')
        nxt = text.find('\n## ', start + 1)
        print(text[start:None if nxt == -1 else nxt].rstrip())
    elif cmd == 'collect':
        CHANGELOG.write_text(merge_into_unreleased(CHANGELOG.read_text(), merged))
        for path in fragment_files():
            path.unlink()
        print(f'Merged into {CHANGELOG.name}; fragments removed.')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
