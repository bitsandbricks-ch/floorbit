"""Traffic categories (issue #1622): the built-in seven plus the tenant's own, the same for every
event of the tenant. Applications, rule sources, the flow classifier, the Traffic page and the
dashboard's "Traffic by kind" all use this list. Docs: docs/applications.md, "Categories".

An own category has an id (``a-z0-9-``), an English and a German name and a colour from ``PALETTE``.
Shared lists (Floorbit's own list, rule sources) stay on the built-in ones; an id this tenant
doesn't know counts as "other" wherever it is read.
"""
import re
import threading

from . import store

FILE = 'traffic-categories.json'
MAX_OWN = 30
NAME_MAX = 40
ID_RE = re.compile(r'^[a-z0-9]([a-z0-9-]{0,28}[a-z0-9])?\Z')

# The built-in ones, in the order the charts stack them. Colours as before (#1408); social is new
# to the charts, which counted it as web until now.
BUILTIN = (
    {'id': 'gaming', 'name': 'Gaming', 'name_de': 'Gaming', 'colour': '#16a34a'},
    {'id': 'streaming', 'name': 'Streaming', 'name_de': 'Streaming', 'colour': '#9333ea'},
    {'id': 'social', 'name': 'Social', 'name_de': 'Soziale Medien', 'colour': '#db2777'},
    {'id': 'downloads', 'name': 'Downloads', 'name_de': 'Downloads', 'colour': '#2563eb'},
    {'id': 'updates', 'name': 'Updates', 'name_de': 'Updates', 'colour': '#d97706'},
    {'id': 'web', 'name': 'Web', 'name_de': 'Web', 'colour': '#0891b2'},
    {'id': 'other', 'name': 'Other', 'name_de': 'Anderes', 'colour': '#94a3b8'},
)
BUILTIN_IDS = tuple(c['id'] for c in BUILTIN)
# Colours an own category may have: apart from the built-in ones, readable on light and dark.
PALETTE = ('#dc2626', '#ea580c', '#ca8a04', '#65a30d', '#0d9488', '#0284c7', '#4f46e5', '#c026d3', '#e11d48',
           '#78716c')

_lock = threading.Lock()


class CategoryError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _path():
    return store.tenant_path(FILE)


def own():
    """The tenant's own categories, as saved; broken entries left out."""
    doc = store.read_json(_path(), {}) or {}
    out, seen = [], set(BUILTIN_IDS)
    for entry in doc.get('categories') or []:
        try:
            clean = _clean(entry)
        except CategoryError:
            continue
        if clean['id'] not in seen:
            seen.add(clean['id'])
            out.append(clean)
    return out


def merged():
    """Every category this tenant has: the built-in ones (marked), then its own."""
    return [{**c, 'builtin': True} for c in BUILTIN] + [{**c, 'builtin': False} for c in own()]


def ids():
    return BUILTIN_IDS + tuple(c['id'] for c in own())


def known(category, allowed=None):
    """The category itself when this tenant has it, else "other"."""
    return category if category in (allowed if allowed is not None else ids()) else 'other'


def colours():
    return {c['id']: c['colour'] for c in merged()}


def _clean(entry):
    if not isinstance(entry, dict):
        raise CategoryError('Each category is an object with an id, names and a colour.')
    cid = str(entry.get('id') or '').strip().lower()
    if not ID_RE.match(cid):
        raise CategoryError('A category id is 1 to 30 lower-case letters, digits and dashes.')
    if cid in BUILTIN_IDS:
        raise CategoryError(f'"{cid}" is a built-in category.')
    name = ' '.join(str(entry.get('name') or '').split())
    name_de = ' '.join(str(entry.get('name_de') or '').split()) or name
    if not 1 <= len(name) <= NAME_MAX or len(name_de) > NAME_MAX:
        raise CategoryError(f'Give the category a name (up to {NAME_MAX} characters).')
    colour = str(entry.get('colour') or '').lower()
    if colour not in PALETTE:
        raise CategoryError('Pick one of the offered colours.')
    return {'id': cid, 'name': name, 'name_de': name_de, 'colour': colour}


def save(entries):
    """Replaces the tenant's own categories. Returns (before, after) for the audit log."""
    if not isinstance(entries, list):
        raise CategoryError('Send the categories as a list.')
    if len(entries) > MAX_OWN:
        raise CategoryError(f'Floorbit keeps at most {MAX_OWN} own categories.')
    clean = [_clean(e) for e in entries]
    found = [c['id'] for c in clean]
    if len(set(found)) != len(found):
        raise CategoryError('Two categories have the same id.')
    names = [c['name'].lower() for c in clean] + [c['name'].lower() for c in BUILTIN]
    if len(set(names)) != len(names):
        raise CategoryError('Two categories have the same name.')
    with _lock:
        before = own()
        store.write_json(_path(), {'categories': clean})
    return before, clean
