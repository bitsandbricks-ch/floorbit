"""The sidebar on every crew page (templates/_nav.html, frontend/src/nav/).

The React pages and the pages Flask draws (floor plan, Settings, users, audit log) show the same
sidebar: the server puts what it needs into the page, so it draws at once, and the pages Flask
draws load it as a second entry of the frontend build.
"""
import json
import os
import re

from flask import current_app, request
from jinja2 import pass_context
from markupsafe import Markup, escape

from . import page_index, spa, store

COOKIE = 'floorbit_nav'
LANG_COOKIE = 'floorbit_lang'
LANGS = ('en', 'de-CH', 'de')


def boot(ctx):
    """Pages, brand and account for the sidebar, from the template context of this request."""
    theme = ctx.get('theme') or {}
    user = ctx.get('current_user')
    account = None
    if user:
        account = {'name': user.get('display_name') or user.get('username'), 'username': user.get('username')}
    return {
        'pages': page_index.for_context(ctx),
        'brand': {'logo': theme.get('logo_url') or None, 'name': theme.get('name') or None},
        'user': account,
        'signOut': bool(ctx.get('auth_enabled')),
        # On a hosted platform the account menu lists the person's other tenants (/api/tenant/mine).
        'hosted': bool(store.hosted_tenant()),
        # Saved with the account; None without sign-in, where the browser keeps them instead.
        'prefs': _prefs(user),
    }


def _prefs(user):
    if not user or user.get('api_token'):
        return None
    auth = current_app.extensions.get('auth')
    record = auth.users.get(user.get('username')) if auth and auth.enabled else None
    if not record:
        return None
    from auth.users import clean_nav  # late: auth imports floorbit while it loads
    return clean_nav(record.get('nav'))


def state():
    """'rail' (folded to icons) or 'full', so the page keeps the sidebar's width before scripts run."""
    return 'rail' if request.cookies.get(COOKIE) == 'rail' else 'full'


def context():
    """Template globals: ``nav_boot()`` (needs the page's context), ``nav_state``, ``nav_assets``
    and ``nav_markup()``."""
    return {'nav_boot': _boot_here, 'nav_state': state(), 'nav_assets': spa.assets(spa.NAV_ENTRY),
            'nav_markup': markup}


# ── the first paint ───────────────────────────────────────────────────────────────
# The sidebar's markup, drawn here so it is in the page before any script: the floor plan's own
# markup and scripts come after it, so the plan can never show up first. The script
# (frontend/src/nav/entry.tsx) takes it over with the same markup (Sidebar.tsx). Icons, order and
# texts come from the build (nav-shell.json, frontend/buildtools/nav-shell.ts).

def _shell():
    path = os.path.join(current_app.static_folder, 'app', 'nav-shell.json')
    cache = current_app.extensions.setdefault('floorbit_nav_shell', {})
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if cache.get('mtime') != mtime:
        try:
            with open(path, encoding='utf-8') as f:
                cache.update(mtime=mtime, shell=json.load(f))
        except (OSError, ValueError):
            return None
    return cache['shell']


def language():
    """The browser's language as the frontend picks it (src/i18n/lang.ts): its cookie, else the
    first Accept-Language we have."""
    saved = request.cookies.get(LANG_COOKIE)
    if saved in LANGS:
        return saved
    for tag in re.split(r'\s*,\s*', request.headers.get('Accept-Language') or ''):
        code = tag.split(';')[0].strip().lower()
        if code in ('de', 'de-ch', 'de-li'):
            return 'de-CH'
        if code.startswith('de'):
            return 'de'
        if code.startswith('en'):
            return 'en'
    return 'en'


def active_href(pages, path):
    """Same as activeHref in sections.ts: the one row to light."""
    best = None
    for p in pages:
        href = p['href']
        if (href == path or (href != '/' and path.startswith(href + '/'))) and (not best or len(href) > len(best)):
            best = href
    return best


def _initials(name):
    parts = [p for p in re.split(r'[\s._-]+', name or '') if p][:2]
    return ''.join(p[0].upper() for p in parts) or '?'


def markup(boot):
    """The sidebar as Sidebar.tsx draws it on first render, or '' without a frontend build."""
    shell = _shell()
    if not shell:
        return ''
    lang = language()
    tx = shell['texts'].get('de-CH' if lang == 'de' else lang) or shell['texts']['en']
    nav_t, page_t = tx['nav'], tx['pages']
    icons = shell['icons']
    pages = boot.get('pages') or []
    rail = state() == 'rail'
    lit = active_href(pages, request.path)
    by_id = {p['id']: p for p in pages}
    known = set(shell['pinned']) | {i for s in shell['sections'] for i in s['pages']}
    pinned = [by_id[i] for i in shell['pinned'] if i in by_id]
    sections = [(s['id'], [by_id[i] for i in s['pages'] if i in by_id]) for s in shell['sections']]
    sections.append(('more', [p for p in pages if p['id'] not in known]))
    sections = [(sid, ps) for sid, ps in sections if ps]
    lit_section = next((sid for sid, ps in sections if any(p['href'] == lit for p in ps)), None)
    e = escape

    def label(p):
        return page_t.get(p['id']) or p['label']

    prefs = boot.get('prefs') or {}
    favs = [by_id[i] for i in prefs.get('favourites') or [] if i in by_id]

    def star(p):
        if rail or 'favAdd' not in nav_t:   # an older build without favourites
            return ''
        fav = p['id'] in (prefs.get('favourites') or [])
        text = e(nav_t['favRemove' if fav else 'favAdd'].replace('{{page}}', label(p)))
        return (f'<button type="button" class="fb-nav-fav" aria-pressed="{"true" if fav else "false"}" '
                f'aria-label="{text}" title="{text}">{icons["starFilled" if fav else "star"]}</button>')

    def row(p):
        cur = ' aria-current="page"' if p['href'] == lit else ''
        title = f' title="{e(label(p))}"' if rail else ''
        icon = icons['page'].get(p['id']) or icons['page']['*']
        return (f'<li class="fb-nav-item"><a href="{e(p["href"])}" class="fb-nav-row"{title}{cur}>{icon}'
                f'<span class="fb-nav-text">{e(label(p))}</span></a>{star(p)}</li>')

    out = [f'<nav class="fb-nav" data-state="{"rail" if rail else "full"}" aria-label="{e(nav_t["label"])}">',
           f'<div class="fb-nav-top"><a href="/" class="fb-nav-brand" title="{e(nav_t["home"])}">'
           f'{_brand(boot, rail)}</a></div>']
    mac = re.search(r'Mac|iPhone|iPad', request.headers.get('User-Agent') or '')
    title = f' title="{e(nav_t["goTo"])}"' if rail else ''
    out.append(f'<button type="button" class="fb-nav-row fb-nav-search"{title} aria-keyshortcuts="Control+K Meta+K">'
               f'{icons["search"]}<span class="fb-nav-text">{e(nav_t["goTo"])}</span>'
               f'<kbd class="fb-nav-kbd">{"⌘K" if mac else "Ctrl K"}</kbd></button>')
    out.append('<div class="fb-nav-scroll">')
    if favs and 'favourites' in nav_t:
        head = '' if rail else f'<div class="fb-nav-group-label">{e(nav_t["favourites"])}</div>'
        out.append(f'<div class="fb-nav-favs">{head}<ul class="fb-nav-list" aria-label="{e(nav_t["favourites"])}">'
                   + ''.join(row(p) for p in favs) + '</ul></div>')
    out.append('<ul class="fb-nav-list">' + ''.join(row(p) for p in pinned) + '</ul>')
    for sid, ps in sections:
        name = nav_t['sections'].get(sid, sid)
        expanded = not rail and sid == lit_section
        lit_attr = ' data-lit="true"' if sid == lit_section else ''
        title = f' title="{e(name)}"' if rail else ''
        icon = icons['section'].get(sid, icons['page']['*'])
        out.append(f'<div class="fb-nav-section"{lit_attr}>'
                   f'<button type="button" class="fb-nav-row fb-nav-section-head" '
                   f'aria-expanded="{"true" if expanded else "false"}"{title}>{icon}'
                   f'<span class="fb-nav-text">{e(name)}</span>{icons["chevron"]}</button>')
        if expanded:
            out.append('<ul class="fb-nav-list fb-nav-sub">' + ''.join(row(p) for p in ps) + '</ul>')
        out.append('</div>')
    out.append('</div>')
    user = boot.get('user')
    name = (user.get('name') or user.get('username')) if user else nav_t['account']
    avatar = e(_initials(name)) if user else icons.get('dots', '')
    signed_in = tx.get('signedInAs', 'Signed in as {{username}}')
    aria = signed_in.replace('{{username}}', user['username'] or '') if user else nav_t['account']
    title = f' title="{e(name)}"' if rail else ''
    fold = nav_t['expand'] if rail else nav_t['collapse']
    out.append('<div class="fb-nav-foot"><div class="fb-nav-account">'
               f'<button type="button" class="fb-nav-row fb-nav-me" aria-expanded="false" aria-haspopup="menu"{title} '
               f'aria-label="{e(aria)}"><span class="fb-nav-avatar" aria-hidden="true">{avatar}</span>'
               f'<span class="fb-nav-text">{e(name)}</span></button></div>'
               f'<button type="button" class="fb-nav-icon-btn fb-nav-fold" aria-label="{e(fold)}" title="{e(fold)}">'
               f'{icons["expand"] if rail else icons["collapse"]}</button></div></nav>')
    tabs = [by_id[i] for i in shell['pinned'] if i in by_id and i in shell['tabs']][:4]
    out.append(f'<nav class="fb-tabbar" aria-label="{e(nav_t["quick"])}">')
    for p in tabs:
        cur = ' aria-current="page"' if p['href'] == lit else ''
        icon = icons['tab'].get(p['id']) or icons['tab']['*']
        out.append(f'<span class="fb-tabbar-cell"><a href="{e(p["href"])}" class="fb-tabbar-item"{cur}>'
                   f'<span class="fb-tabbar-icon">{icon}</span>'
                   f'<span class="fb-tabbar-label">{e(label(p))}</span></a></span>')
    out.append('<span class="fb-tabbar-cell"><button type="button" class="fb-tabbar-item" aria-expanded="false" '
               f'aria-controls="fb-sheet"><span class="fb-tabbar-icon">{icons["menu"]}</span>'
               f'<span class="fb-tabbar-label">{e(nav_t["menu"])}</span></button></span></nav>')
    return Markup(''.join(out))  # every text above is escaped; the icons come from our build


def _brand(boot, rail):
    """Brand() in Sidebar.tsx: an event logo, an event name, or Floorbit's lockup."""
    brand = boot.get('brand') or {}
    if brand.get('logo'):
        alt = escape(brand.get('name') or 'Event logo')
        return f'<img class="fb-nav-logo" src="{escape(brand["logo"])}" alt="{alt}"/>'
    if rail or brand.get('name'):
        name = f'<span class="fb-brand-name">{escape(brand["name"])}</span>' if not rail and brand.get('name') else ''
        mark = '<span class="fb-brand-mark" role="img" aria-label="Floorbit"></span>'
        return f'<span class="fb-brand">{mark}{name}</span>'
    return '<span class="fb-brand"><span class="fb-brand-lockup" role="img" aria-label="Floorbit"></span></span>'


@pass_context
def _boot_here(ctx):
    return boot(ctx)
