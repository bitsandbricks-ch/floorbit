"""The hosted platform: which tenants it runs, and who belongs to more than one (issue #466).

Hosted Floorbit runs one process per tenant (``FLOORBIT_TENANT``, docs/tenancy.md). The platform's
own list of tenants is ``platform.json``, beside ``tenants/`` in the state folder or database every
tenant shares. A platform admin adds tenants with ``flask tenants add``; there is no sign-up.

A person keeps one account per tenant, with that tenant's role. Accounts in two tenants are the same
person when they are linked to the same outside login: the same Discord account, or the same subject
at the same OIDC issuer. Password accounts are never matched, because a username says nothing about
who is behind it. Such a person sees their other tenants in the account menu and opens them there.
"""
import os
import threading
from urllib.parse import urlsplit

from . import store

PLATFORM_FILE = 'platform.json'
_lock = threading.Lock()


class HostingError(ValueError):
    pass


def path():
    return os.path.join(store.state_folder(), PLATFORM_FILE)


def _folder(tenant_id):
    return f'{store.TENANTS_FOLDER}/{tenant_id}'


def _clean_url(url):
    url = (url or '').strip().rstrip('/')
    if not url:
        return ''
    parts = urlsplit(url)
    local = parts.hostname in ('localhost', '127.0.0.1')
    if parts.scheme not in ('https', 'http') or not parts.hostname or (parts.scheme == 'http' and not local) \
            or parts.username or parts.password:
        raise HostingError('The address is a URL like https://club.example.com (http only for localhost).')
    return url


def tenants():
    """The platform's tenants, in the order they were added: ``[{id, name, url}]``."""
    out, seen = [], set()
    for t in (store.read_json(path(), {}) or {}).get('tenants') or []:
        tid = t.get('id') if isinstance(t, dict) else None
        if not isinstance(tid, str) or not store._TENANT_RE.match(tid) or tid in seen:
            continue
        seen.add(tid)
        out.append({'id': tid, 'name': str(t.get('name') or ''), 'url': str(t.get('url') or '')})
    return out


def add(tenant_id, name='', url=''):
    """List a tenant on the platform. Its documents start empty, in ``tenants/<id>/``."""
    tenant_id = (tenant_id or '').strip()
    if not store._TENANT_RE.match(tenant_id):
        raise HostingError('A tenant name is lower-case letters, digits and -, at most 40.')
    entry = {'id': tenant_id, 'name': (name or '').strip()[:80], 'url': _clean_url(url)}
    with _lock:
        listed = tenants()
        if any(t['id'] == tenant_id for t in listed):
            raise HostingError(f'There already is a tenant called {tenant_id}.')
        store.write_json(path(), {'tenants': [*listed, entry]})
    return entry


def tenant_data(tenant_id):
    """Another tenant's own documents (accounts, settings), read from the shared storage."""
    with store.using(tenant=_folder(tenant_id), event=''):
        return store.read_json(store.tenant_file(), {}) or {}


def _issuer(data, provider):
    config = (data.get('auth_oidc') or {}).get(provider)
    return (config.get('issuer') or '').rstrip('/') if isinstance(config, dict) else None


def memberships(user):
    """The other tenants where this account's person has an account too: ``[{id, name, url, username}]``.
    ``user`` is the full account record of this tenant. Empty on a self-hosted install."""
    here = store.hosted_tenant()
    links = {p: s for p, s in ((user or {}).get('identities') or {}).items() if s}
    if not here or not links:
        return []
    mine = store.read_json(store.tenant_file(), {}) or {}
    out = []
    for tenant in tenants():
        if tenant['id'] == here:
            continue
        data = tenant_data(tenant['id'])
        for account in (data.get('auth_users') or {}).values():
            theirs = account.get('identities') or {}
            # An OIDC subject is only unique at its issuer, and each tenant sets up its own.
            if any(theirs.get(p) == s and _issuer(mine, p) == _issuer(data, p) for p, s in links.items()):
                out.append({**tenant, 'username': account.get('username')})
                break
    return out


def register_cli(app):
    import click
    from flask.cli import AppGroup

    group = AppGroup('tenants', help='The tenants of a hosted Floorbit.')

    @group.command('add')
    @click.argument('tenant_id')
    @click.option('--name', default='', help='The club or organisation, as people know it.')
    @click.option('--url', default='', help='Where its Floorbit answers, like https://club.example.com.')
    @click.option('--admin', 'admin', default=None, help='Also add its first admin account.')
    @click.option('--password', default=None, help='The admin\'s password; prompted for when left out.')
    def add_tenant(tenant_id, name, url, admin, password):
        from auth.users import UserError, UserStore  # late: auth imports floorbit while it loads
        try:
            add(tenant_id, name, url)
        except HostingError as exc:
            raise click.ClickException(str(exc)) from None
        click.echo(f'Added the tenant {tenant_id}. Start its Floorbit with {store.TENANT_ENV}={tenant_id}.')
        if admin:
            if password is None:
                password = click.prompt('Password', hide_input=True, confirmation_prompt=True)
            with store.using(tenant=_folder(tenant_id), event=''):
                try:
                    UserStore(store.tenant_file).add(admin, password, role='admin')
                except UserError as exc:
                    raise click.ClickException(str(exc)) from None
            click.echo(f'Added {admin} as its admin.')

    @group.command('list')
    def list_tenants():
        rows = tenants()
        if not rows:
            click.echo('No tenants yet.')
        for t in rows:
            click.echo(f"{t['id']:<24} {t['name']:<32} {t['url']}")

    app.cli.add_command(group)
