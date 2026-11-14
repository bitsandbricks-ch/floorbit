"""Themes: which preset and colours a page renders with, and the uploaded event logo.

Every page's ``<html>`` gets its theme from ``theme_context()`` (a template context
processor), so the first paint already has the right colours. The site default comes from
Settings > Appearance; one screen can pick another preset with ``?theme=<preset>``, which is
kept in a cookie so a kiosk browser stays on it after a reload. See docs/themes.md.
"""
import base64
import hashlib
import re

from flask import Response, abort, request
from markupsafe import Markup, escape

from .settings import THEME_PRESETS

PRESETS = [p['value'] for p in THEME_PRESETS]
COOKIE = 'floorbit_theme'
DARK_ONLY = {'kiosk', 'classic'}
INK, WHITE = '#0b0b0f', '#ffffff'


# ── Colour maths (WCAG relative luminance) ────────────────────────────────────────────
def _rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def luminance(hex_color):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _mix(a, b, weight):
    """``weight`` of colour b into colour a."""
    return '#' + ''.join(f'{round(x + (y - x) * weight):02x}' for x, y in zip(_rgb(a), _rgb(b), strict=True))


# ── What a page renders with ──────────────────────────────────────────────────────────
def custom_seeds(values):
    """CSS seeds for the custom preset, filling in what the admin left empty."""
    bg, surface, fg, accent = (values.get(k) or '' for k in ('background', 'surface', 'text', 'accent'))
    seeds, scheme = {}, None
    if bg:
        scheme = 'dark' if luminance(bg) < 0.4 else 'light'
        fg = fg or ('#f4f4f5' if scheme == 'dark' else '#111118')
        surface = surface or _mix(bg, fg, 0.06)
        seeds.update({'--theme-bg': bg, '--theme-surface': surface, '--theme-fg': fg})
    else:
        if surface:
            seeds['--theme-surface'] = surface
        if fg:
            seeds['--theme-fg'] = fg
    if accent:
        seeds['--theme-accent'] = accent
        # Ink or white on accent fills, whichever reads better.
        seeds['--theme-on-accent'] = INK if contrast(accent, INK) >= contrast(accent, WHITE) else WHITE
    return seeds, scheme


def logo_version(data_url):
    return hashlib.sha256(data_url.encode()).hexdigest()[:10] if data_url else ''


def resolve(store, page=None, override=None):
    """The theme for one page: preset, locked light/dark, inline seeds, name and logo."""
    preset = store.get('theme.preset')
    if override in PRESETS:
        preset = override
    elif page == 'kiosk' and preset == 'floorbit':
        preset = 'kiosk'   # the big screen reads from across the hall unless told otherwise

    style, scheme = {}, ('dark' if preset in DARK_ONLY else None)
    if preset == 'custom':
        style, scheme = custom_seeds({k: store.get('theme.' + k)
                                      for k in ('accent', 'background', 'surface', 'text')})

    logo = store.get('theme.logo')
    return {
        'preset': preset,
        'scheme': scheme,
        'style': ';'.join(f'{k}:{v}' for k, v in style.items()),
        'name': store.get('theme.name'),
        'logo_url': f'/brand/logo?v={logo_version(logo)}' if logo else '',
    }


def html_attrs(theme):
    attrs = [f'data-preset="{escape(theme["preset"])}"']
    if theme['scheme']:
        # theme.js sees the lock and leaves light/dark alone; the toggle hides.
        attrs.append(f'data-theme="{theme["scheme"]}" data-theme-lock="{theme["scheme"]}"')
    if theme['style']:
        attrs.append(f'style="{escape(theme["style"])}"')
    return Markup(' '.join(attrs))


def _request_override():
    wanted = request.args.get('theme', '').strip().lower()
    if wanted in PRESETS:
        return wanted
    if wanted == 'default':
        return None
    return request.cookies.get(COOKIE) if request.cookies.get(COOKIE) in PRESETS else None


def init_theme(app, store):
    """Register the template context, the ?theme= cookie and the /brand/logo route."""

    @app.context_processor
    def theme_context():
        # The health wall and the stats screen are big screens too: they get the kiosk preset unless
        # the theme says otherwise.
        path = request.path.rstrip('/')
        big = path in ('/kiosk', '/health') or (path == '/stats' and request.args.get('screen') == '1')
        page = 'kiosk' if big else None
        theme = resolve(store, page=page, override=_request_override())
        theme['html_attrs'] = html_attrs(theme)
        return {'theme': theme}

    @app.after_request
    def remember_screen_theme(response):
        wanted = request.args.get('theme', '').strip().lower()
        if wanted in PRESETS:
            response.set_cookie(COOKIE, wanted, max_age=365 * 86400, samesite='Lax', httponly=True)
        elif wanted == 'default':
            response.delete_cookie(COOKIE)
        return response

    from auth import public_endpoint

    @app.route('/brand/logo')
    @public_endpoint
    def brand_logo():
        data_url = store.get('theme.logo')
        m = re.fullmatch(r'data:([\w/+.-]+);base64,(.+)', data_url or '', flags=re.S)
        if not m:
            abort(404)
        resp = Response(base64.b64decode(m.group(2)), mimetype=m.group(1))
        # An uploaded SVG is a document: never let it run script if opened directly.
        resp.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable' if request.args.get('v') else 'no-cache'
        return resp
