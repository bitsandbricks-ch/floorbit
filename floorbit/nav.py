"""The sidebar on every crew page (templates/_nav.html, frontend/src/nav/).

The React pages and the pages Flask draws (floor plan, Settings, users, audit log) show the same
sidebar: the server puts what it needs into the page, so it draws at once, and the pages Flask
draws load it as a second entry of the frontend build.
"""
from flask import request
from jinja2 import pass_context

from . import page_index, spa

COOKIE = 'floorbit_nav'


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
    }


def state():
    """'rail' (folded to icons) or 'full', so the page keeps the sidebar's width before scripts run."""
    return 'rail' if request.cookies.get(COOKIE) == 'rail' else 'full'


def context():
    """Template globals: ``nav_boot()`` (needs the page's context), ``nav_state`` and ``nav_assets``."""
    return {'nav_boot': _boot_here, 'nav_state': state(), 'nav_assets': spa.assets(spa.NAV_ENTRY)}


@pass_context
def _boot_here(ctx):
    return boot(ctx)
