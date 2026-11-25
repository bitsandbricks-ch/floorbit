"""What the sidebar needs, put into every page (templates/_nav.html).

The React app draws the sidebar (frontend/src/nav/); the server hands it the pages this account
may open, the brand and the account with the page, so it draws at once without an API call.
"""
from flask import current_app
from jinja2 import pass_context

from . import hosting, nav_sections, page_index


def boot(ctx):
    """Pages, brand and account for the sidebar, from the template context of this request."""
    theme = ctx.get('theme') or {}
    user = ctx.get('current_user')
    account = None
    if user:
        account = {'name': user.get('display_name') or user.get('username'), 'username': user.get('username')}
        if user.get('platform'):
            account['platform'] = True   # a platform admin visiting (floorbit/tenant_switch.py)
    pages = page_index.for_context(ctx)
    pages += _plugin_pages()
    return {
        'pages': pages,
        'custom': nav_sections.for_pages(pages),
        'brand': {'logo': theme.get('logo_url') or None, 'name': theme.get('name') or None},
        'user': account,
        'signOut': bool(ctx.get('auth_enabled')),
        # With more than one tenant the tenant switcher asks for the person's other ones (/api/tenant/mine).
        'tenants': hosting.several(),
        # Saved with the account; None without sign-in, where the browser keeps them instead.
        'prefs': _prefs(user),
    }


def _plugin_pages():
    """The plugins' own pages (plugin.yaml ``pages:``) this account may open, for the Plugins section."""
    if 'floorbit_plugins' not in current_app.extensions:
        return []
    from .blueprints.plugins import _language, plugin_pages  # late: the blueprint imports this module's app
    return plugin_pages(_language())


def _prefs(user):
    if not user or user.get('api_token'):
        return None
    auth = current_app.extensions.get('auth')
    record = auth.users.get(user.get('username')) if auth and auth.enabled else None
    if not record:
        return None
    from auth.users import clean_nav  # late: auth imports floorbit while it loads
    return clean_nav(record.get('nav'))


def context():
    """Template globals: ``nav_boot()``, which needs the page's context."""
    return {'nav_boot': _boot_here}


@pass_context
def _boot_here(ctx):
    return boot(ctx)
