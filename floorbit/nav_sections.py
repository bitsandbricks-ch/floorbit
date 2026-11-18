"""Sidebar sections admins make themselves (docs/navigation.md#your-own-sections).

A section has a ``name``, an ``icon`` (one of :data:`ICONS`, drawn by frontend/src/nav/sections.ts)
and ``links``. A link is

- ``dashboard``: a dashboard by id (floorbit/dashboards.py), shown with the dashboard's name;
- ``page``: one of the pages in floorbit/page_index.py, by id;
- ``url``: an address of its own, a path on this server (``/plan?seat=A-1``) or ``http(s)://``.

Every link may have a ``label`` of its own. Each person sees only the links they may open: a page
they can't open, or a dashboard that's gone, is left out, and a section left with nothing is too.

Kept in data.json under ``nav_sections``, in the order the admin put them.
"""
import re
import threading
import time

from . import dashboards, page_index
from .store import load_data, save_data

KEY = 'nav_sections'
MAX_SECTIONS = 12
MAX_LINKS = 20
NAME_MAX = 40
LABEL_MAX = 60
URL_MAX = 500
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}\Z')
KINDS = ('dashboard', 'page', 'url')
# The icons a section can have; the same names as CUSTOM_ICONS in frontend/src/nav/sections.ts.
ICONS = ('dashboard', 'star', 'bolt', 'network', 'server', 'chart', 'heart', 'users', 'trophy', 'calendar',
         'wifi', 'shield', 'tools', 'book', 'flag', 'gamepad', 'bell', 'eye', 'folder', 'link', 'map', 'screen')
_PAGE_IDS = {p[1] for p in page_index.PAGES}
_lock = threading.Lock()


class SectionError(ValueError):
    pass


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _slug(name, taken):
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:24] or 'section'
    slug, n = base, 2
    while slug in taken:
        slug, n = f'{base}-{n}', n + 1
    return slug


def _url(value):
    url = str(value or '').strip()
    # Our own paths, or a web address: never javascript: or a protocol-relative //host.
    if len(url) <= URL_MAX and (re.match(r'^/(?![/\\])', url) or re.match(r'^https?://[^\s/]', url, re.I)) \
            and not re.search(r'\s', url):
        return url
    raise SectionError('A link goes to a path on this server (/plan) or a web address (https://example.com).')


def _link(raw):
    if not isinstance(raw, dict):
        raise SectionError('Each link is a JSON object.')
    kind = raw.get('kind')
    if kind not in KINDS:
        raise SectionError('A link goes to a dashboard, a page or an address.')
    link = {'kind': kind}
    if kind == 'dashboard':
        ref = str(raw.get('ref') or '').strip().lower()
        if not dashboards.ID_RE.match(ref):
            raise SectionError('Pick the dashboard the link opens.')
        link['ref'] = ref
    elif kind == 'page':
        ref = str(raw.get('ref') or '')
        if ref not in _PAGE_IDS:
            raise SectionError('Pick the page the link opens.')
        link['ref'] = ref
    else:
        link['href'] = _url(raw.get('href'))
    label = _text(raw.get('label'), LABEL_MAX)
    if label:
        link['label'] = label
    elif kind == 'url':
        raise SectionError('A link to an address needs a name.')
    return link


def clean(body):
    """The sections as sent (``{"sections": [...]}``), checked; raises :class:`SectionError`."""
    raw = body.get('sections') if isinstance(body, dict) else None
    if not isinstance(raw, list):
        raise SectionError('Send {"sections": [...]}.')
    if len(raw) > MAX_SECTIONS:
        raise SectionError(f'The sidebar has room for {MAX_SECTIONS} sections of your own.')
    out, taken = [], set()
    for s in raw:
        if not isinstance(s, dict):
            raise SectionError('Each section is a JSON object.')
        name = _text(s.get('name'), NAME_MAX)
        if not name:
            raise SectionError('Every section needs a name.')
        links = s.get('links') if isinstance(s.get('links'), list) else []
        if len(links) > MAX_LINKS:
            raise SectionError(f'A section holds up to {MAX_LINKS} links.')
        sid = str(s.get('id') or '').strip().lower()
        if not ID_RE.match(sid) or sid in taken:
            sid = _slug(name, taken)
        taken.add(sid)
        out.append({'id': sid, 'name': name, 'icon': s.get('icon') if s.get('icon') in ICONS else 'folder',
                    'links': [_link(x) for x in links]})
    return out


def saved(data=None):
    data = load_data() if data is None else data
    raw = data.get(KEY)
    sections = raw.get('sections') if isinstance(raw, dict) else None
    try:
        return clean({'sections': sections or []})
    except SectionError:
        return []   # a hand-edited data.json shouldn't take the sidebar down


def save(body, by):
    sections = clean(body)
    with _lock:
        data = load_data()
        data[KEY] = {'sections': sections, 'updated_at': time.time(), 'by': by}
        save_data(data)
    return sections


def for_pages(pages, data=None):
    """The sections as this person sees them, for the sidebar: ``pages`` are the ones they may open
    (page_index.for_context). Links become ``{href, label, kind, page?}``; empty sections go."""
    data = load_data() if data is None else data
    by_id = {p['id']: p for p in pages}
    boards = {b['id']: b for b in dashboards.all_layouts(data)} if 'dashboards' in by_id else {}
    out = []
    for s in saved(data):
        links = []
        for link in s['links']:
            if link['kind'] == 'dashboard':
                board = boards.get(link['ref'])
                if board:
                    links.append({'kind': 'dashboard', 'href': f"/dashboards/{board['id']}",
                                  'label': link.get('label') or board.get('name') or board['id']})
            elif link['kind'] == 'page':
                page = by_id.get(link['ref'])
                if page:
                    # No label of its own: the page's name, in the reader's language (goto.pages).
                    links.append({'kind': 'page', 'href': page['href'], 'page': page['id'],
                                  'label': link.get('label') or page['label'], 'own': bool(link.get('label'))})
            else:
                links.append({'kind': 'url', 'href': link['href'], 'label': link['label'],
                              'external': not link['href'].startswith('/')})
        if links:
            out.append({'id': s['id'], 'name': s['name'], 'icon': s['icon'], 'links': links})
    return out
