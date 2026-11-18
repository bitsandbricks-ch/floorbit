"""The shared icon library: SVG icons admins upload for inventory devices, groups, tags and plan icons.

An uploaded SVG is rebuilt from an allowlist, never stored as sent: only plain shapes and their
geometry survive, so no script, event handler, link, external reference, embedded image,
``foreignObject`` or CSS gets through. Colours become ``currentColor`` so the icon takes the colour
picked for the item. The page shows icons as CSS masks (an image, never inline markup), which
would keep a missed attack inert anyway; the sanitiser is the first line, not the only one.

Icons are stored in ``data['custom_icons']`` as ``{"id", "name", "svg", "by", "at"}``. The id is
``custom-`` plus a hash of the cleaned SVG, so the same icon uploaded twice is one icon and the
served file never changes under its id (it can be cached for good).
"""
import base64
import hashlib
import re
import time
import xml.etree.ElementTree as ET

KEY = 'custom_icons'
PREFIX = 'custom-'
MAX_BYTES = 64 * 1024        # what may be uploaded
MAX_CLEAN = 48 * 1024        # what is kept after cleaning
MAX_ICONS = 300
MAX_ELEMENTS = 2000
MAX_DEPTH = 32             # groups in groups: real icons stay under ten
NAME_MAX = 40
ID_RE = re.compile(r'^custom-[0-9a-f]{12}$')
# What a floor plan icon shows once its uploaded icon is removed (floorbit/plan_icons.py).
PLAN_FALLBACK = 'info'

SVG_NS = 'http://www.w3.org/2000/svg'

# Shapes and the few containers they need. No <use>, <image>, <a>, <style>, <script>,
# <foreignObject>, <animate*>, <set>, <filter> or <pattern>: each can load, run or link something.
ELEMENTS = {
    'svg', 'g', 'path', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'rect', 'title', 'desc',
    'defs', 'clipPath', 'mask', 'linearGradient', 'radialGradient', 'stop',
}
GEOMETRY = {
    'd', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'width', 'height', 'points',
    'transform', 'pathLength', 'offset', 'gradientUnits', 'gradientTransform', 'fx', 'fy',
    'clipPathUnits', 'maskUnits', 'maskContentUnits', 'id',
}
PAINT = {'fill', 'stroke', 'stop-color', 'color'}
PRESENTATION = {
    'fill-rule', 'clip-rule', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit',
    'stroke-dasharray', 'stroke-dashoffset', 'fill-opacity', 'stroke-opacity', 'opacity', 'stop-opacity',
    'clip-path', 'mask', 'vector-effect',
}
ROOT_ONLY = {'viewBox', 'preserveAspectRatio'}
# clip-path="url(#a)" and fill="url(#g)" may point inside the icon, nowhere else.
LOCAL_REF = re.compile(r'^url\(\s*#[A-Za-z_][\w.-]{0,60}\s*\)$')
SAFE_VALUE = re.compile(r'^[\w\s.,#%()+-]{0,4000}$')
D_VALUE = re.compile(r'^[\w\s.,+-]{0,40000}$')


class IconError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _local(tag):
    """'{http://www.w3.org/2000/svg}path' -> 'path'; anything in another namespace -> None."""
    if tag.startswith('{'):
        ns, _, name = tag[1:].partition('}')
        return name if ns == SVG_NS else None
    return tag


def _paint(value):
    v = value.strip()
    if v in ('none', 'transparent'):
        return v
    if LOCAL_REF.match(v):
        return v
    # Every real colour becomes the item's colour; 'currentColor' stays.
    return 'currentColor'


def _attr_ok(name, value, root):
    if name in ROOT_ONLY:
        return root and SAFE_VALUE.match(value) is not None
    if name == 'd' or name == 'points':
        return D_VALUE.match(value) is not None
    if name in ('clip-path', 'mask'):
        return LOCAL_REF.match(value.strip()) is not None
    if name in GEOMETRY or name in PRESENTATION:
        return SAFE_VALUE.match(value) is not None and 'url' not in value.lower()
    return False


def _copy(src, root=False, budget=None, depth=0):
    name = _local(src.tag) if isinstance(src.tag, str) else None
    if name not in ELEMENTS or (name == 'svg' and not root):
        return None
    budget[0] -= 1
    if budget[0] < 0:
        raise IconError('The SVG has too many parts for an icon.')
    if depth > MAX_DEPTH:      # else <g><g><g>... ran out of stack: a 500
        raise IconError('The SVG is nested too deeply for an icon.')
    out = ET.Element(name)
    for key, value in src.attrib.items():
        attr = _local(key)
        if attr is None:      # xlink:href, xml:base, foreign namespaces
            continue
        if attr in PAINT:
            out.set(attr, _paint(value))
        elif _attr_ok(attr, value, root):
            out.set(attr, value.strip())
    if name in ('title', 'desc'):
        out.text = (src.text or '')[:200]
        return out
    for child in src:
        copied = _copy(child, budget=budget, depth=depth + 1)
        if copied is not None:
            out.append(copied)
    return out


def sanitize(raw):
    """The cleaned SVG text, or IconError. Accepts str or bytes."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise IconError('The file is not an SVG (UTF-8 text).') from None
    if not isinstance(raw, str) or not raw.strip():
        raise IconError('Choose an SVG file.')
    if len(raw.encode('utf-8')) > MAX_BYTES:
        raise IconError(f'An icon is at most {MAX_BYTES // 1024} KB.', 413)
    # No DTDs at all: entities are how XML bombs and external fetches get in.
    if re.search(r'<!(DOCTYPE|ENTITY)', raw, re.IGNORECASE):
        raise IconError('The SVG has a DOCTYPE or entities; save it as plain SVG.')
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError:
        raise IconError('The file is not a valid SVG.') from None
    if _local(tree.tag) != 'svg':
        raise IconError('The file is not a valid SVG.')
    clean = _copy(tree, root=True, budget=[MAX_ELEMENTS])
    if not clean.get('viewBox'):
        w, h = tree.get('width', ''), tree.get('height', '')
        w, h = re.sub(r'[^\d.]', '', w), re.sub(r'[^\d.]', '', h)
        if not (w and h):
            raise IconError('The SVG needs a viewBox (or a width and height).')
        clean.set('viewBox', f'0 0 {w} {h}')
    if not any(c.tag not in ('title', 'desc', 'defs') for c in clean):
        raise IconError('The SVG has nothing to draw once cleaned.')
    clean.set('xmlns', SVG_NS)
    clean.set('fill', clean.get('fill') or 'currentColor')
    text = ET.tostring(clean, encoding='unicode')
    if len(text.encode('utf-8')) > MAX_CLEAN:
        raise IconError(f'An icon is at most {MAX_CLEAN // 1024} KB once cleaned.', 413)
    return text


def _clean_name(name):
    name = ' '.join(str(name or '').split())[:NAME_MAX]
    if not name:
        raise IconError('Give the icon a name.')
    return name


def icons(data):
    return [i for i in data.get(KEY) or [] if isinstance(i, dict) and ID_RE.match(str(i.get('id', '')))]


def find(data, icon_id):
    return next((i for i in icons(data) if i['id'] == icon_id), None)


def is_custom(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def exists(icon_id, data=None):
    if data is None:
        from .store import load_data
        data = load_data()
    return find(data, icon_id) is not None


def public(icon):
    return {'id': icon['id'], 'name': icon['name'], 'url': f"/api/icons/{icon['id']}.svg",
            'by': icon.get('by') or '', 'at': icon.get('at')}


def data_uri(data, icon_id):
    """The icon as a ``data:`` URI, so a plan drawing carries it: the kiosk, the attendee pages and an
    exported picture need no second request (and no ``floorplan.view``) to show it."""
    icon = find(data, icon_id)
    return None if icon is None else 'data:image/svg+xml;base64,' + base64.b64encode(icon['svg'].encode()).decode()


def data_uris(data, ids):
    """``{id: data URI}`` of the uploaded icons among ``ids``; removed ones are left out."""
    return {i: u for i in sorted({i for i in ids if is_custom(i)}) if (u := data_uri(data, i))}


def listing(data):
    return [public(i) for i in sorted(icons(data), key=lambda i: i['name'].lower())]


def add(data, name, svg, user=None):
    """Adds the icon (or returns the same one already there) and whether it is new."""
    clean = sanitize(svg)
    icon_id = PREFIX + hashlib.sha256(clean.encode('utf-8')).hexdigest()[:12]
    have = find(data, icon_id)
    if have:
        return have, False
    if len(icons(data)) >= MAX_ICONS:
        raise IconError(f'The library holds at most {MAX_ICONS} icons; remove one first.', 409)
    icon = {'id': icon_id, 'name': _clean_name(name), 'svg': clean, 'by': user or '', 'at': int(time.time())}
    data[KEY] = [*icons(data), icon]
    return icon, True


def rename(data, icon_id, name):
    icon = find(data, icon_id)
    if icon is None:
        raise IconError('No such icon', 404)
    icon['name'] = _clean_name(name)
    return icon


def remove(data, icon_id):
    """Removes the icon; devices, groups and tags that showed it fall back to their default, and
    icons on the floor plan to the plain info icon (so they stay where they are, visible).
    Returns how many used it."""
    if find(data, icon_id) is None:
        raise IconError('No such icon', 404)
    data[KEY] = [i for i in icons(data) if i['id'] != icon_id]
    used = 0
    holders = [*(data.get('inventory') or [])]
    from . import inventory_scope
    holders += [*(data.get(inventory_scope.GROUPS) or []), *(data.get(inventory_scope.TAGS) or [])]
    for holder in holders:
        if isinstance(holder, dict) and holder.get('icon') == icon_id:
            holder['icon'] = ''
            used += 1
    from . import plan_marks
    for mark in data.get(plan_marks.KEY) or []:
        if isinstance(mark, dict) and mark.get('kind') == 'icon' and mark.get('icon') == icon_id:
            mark['icon'] = PLAN_FALLBACK
            used += 1
    return used
