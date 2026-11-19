"""The platform: which tenants it runs, and who belongs to more than one (issue #466).

Every Floorbit is a platform with at least one tenant, ``default``: a self-hosted install is just a
platform nobody added a second tenant to, so it runs the same code as a hosted one. Each process
serves one tenant (``FLOORBIT_TENANT``, else ``default``; docs/tenancy.md). The platform's list of
tenants is ``platform.json``, beside ``tenants/`` in the state folder or database every tenant
shares. A platform admin adds tenants with ``flask tenants add``; there is no sign-up.

A person keeps one account per tenant, with that tenant's role. Accounts in two tenants are the same
person when they are linked to the same outside login: the same Discord account, or the same subject
at the same OIDC issuer. Password accounts are never matched, because a username says nothing about
who is behind it. Such a person sees their other tenants in the account menu and opens them there.
"""
import os
import re
import threading
import time
from urllib.parse import urlsplit

from . import store

PLATFORM_FILE = 'platform.json'
_lock = threading.Lock()


class HostingError(ValueError):
    pass


def path():
    return os.path.join(store.state_folder(), PLATFORM_FILE)


def _folder(tenant_id):
    return store.tenant_folder(tenant_id)


STATUSES = ('active', 'suspended')


def _default():
    return {'id': store.DEFAULT_TENANT, 'name': '', 'url': '', 'status': 'active'}


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


def _doc():
    doc = store.read_json(path(), {}) or {}
    return doc if isinstance(doc, dict) else {}


def _listed():
    return _doc().get('tenants') or []


def _save(**changes):
    # platform.json holds more than the list (the agents' domain): keep what this write doesn't change.
    store.write_json(path(), {**_doc(), **changes})


def tenants():
    """The platform's tenants, in the order they were added: ``[{id, name, url, status}]``. The default
    tenant is always first, written down or not: platform.json only appears with a second tenant,
    so an install that never adds one (and every install from before tenants) needs no file at all."""
    out, seen = [], set()
    listed = _listed()
    if not any(isinstance(t, dict) and t.get('id') == store.DEFAULT_TENANT for t in listed):
        listed = [_default(), *listed]
    for t in listed:
        tid = t.get('id') if isinstance(t, dict) else None
        if not isinstance(tid, str) or not store._TENANT_RE.match(tid) or tid in seen:
            continue
        seen.add(tid)
        status = t.get('status') if t.get('status') in STATUSES and tid != store.DEFAULT_TENANT else 'active'
        out.append({'id': tid, 'name': str(t.get('name') or ''), 'url': str(t.get('url') or ''), 'status': status})
    return out


def find(tenant_id):
    return next((t for t in tenants() if t['id'] == tenant_id), None)


def several():
    """Whether the platform has more than the default tenant: only then is there anything about
    tenants to show."""
    return len(tenants()) > 1


def add(tenant_id, name='', url=''):
    """List a tenant on the platform. Its documents start empty, in ``tenants/<id>/``."""
    tenant_id = (tenant_id or '').strip()
    if not store._TENANT_RE.match(tenant_id):
        raise HostingError('A tenant name is lower-case letters, digits and -, at most 40.')
    entry = {'id': tenant_id, 'name': (name or '').strip()[:80], 'url': _clean_url(url), 'status': 'active'}
    with _lock:
        listed = tenants()
        if any(t['id'] == tenant_id for t in listed):
            raise HostingError(f'There already is a tenant called {tenant_id}.')
        _save(tenants=[*listed, entry])
    return entry


def update(tenant_id, name=None, url=None, status=None):
    """Rename a tenant, change its address, or suspend it and take it back. The default tenant is
    the platform's own: it can't be suspended, or nobody could take a suspension back."""
    with _lock:
        listed = tenants()
        entry = next((t for t in listed if t['id'] == tenant_id), None)
        if entry is None:
            raise HostingError('There is no such tenant.')
        if name is not None:
            entry['name'] = str(name).strip()[:80]
        if url is not None:
            entry['url'] = _clean_url(url)
        if status is not None:
            if status not in STATUSES:
                raise HostingError('A tenant is active or suspended.')
            if tenant_id == store.DEFAULT_TENANT and status != 'active':
                raise HostingError("The default tenant runs the platform and can't be suspended.")
            entry['status'] = status
        _save(tenants=listed)
    _status_cache.clear()
    return entry


# Every request of a tenant asks whether it is suspended: a short memory keeps that from being a
# read of platform.json each time. A suspension reaches every process within this many seconds.
STATUS_RECHECK = 10.0
_status_cache = {}


def suspended(now=None):
    """Whether the platform suspended the tenant this process serves."""
    from .database import DatabaseUnavailable
    tenant = store.current_tenant()
    if tenant == store.DEFAULT_TENANT:
        return False
    now = time.monotonic() if now is None else now
    hit = _status_cache.get(tenant)
    if hit and now - hit[0] < STATUS_RECHECK:
        return hit[1]
    try:
        entry = find(tenant)
        found = bool(entry and entry['status'] == 'suspended')
    except DatabaseUnavailable:
        found = hit[1] if hit else False     # the database being away is not a suspension
    _status_cache[tenant] = (now, found)
    return found


DOMAIN_RE = re.compile(r'^(?=.{4,200}\Z)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z')


def agent_domain():
    """The domain the agents' public certificates are made under (``<tenant>.agent.<domain>``,
    floorbit/public_cert.py), or '' when the platform has none: then agents keep Floorbit's own CA."""
    found = str(_doc().get('agent_domain') or '').strip().lower()
    return found if DOMAIN_RE.match(found) else ''


def set_agent_domain(domain):
    domain = (domain or '').strip().lower().rstrip('.')
    if domain and not DOMAIN_RE.match(domain):
        raise HostingError('The domain is a name like example.com.')
    with _lock:
        _save(agent_domain=domain)
    return domain


def tenant_data(tenant_id):
    """Another tenant's own documents (accounts, settings), read from the shared storage."""
    with store.using(tenant=_folder(tenant_id), event=''):
        return store.read_json(store.tenant_file(), {}) or {}


def _issuer(data, provider):
    config = (data.get('auth_oidc') or {}).get(provider)
    return (config.get('issuer') or '').rstrip('/') if isinstance(config, dict) else None


def memberships(user):
    """The other tenants where this account's person has an account too: ``[{id, name, url, username}]``.
    ``user`` is the full account record of this tenant. Empty while the platform has one tenant."""
    here = store.current_tenant()
    links = {p: s for p, s in ((user or {}).get('identities') or {}).items() if s}
    if not links or not several():
        return []
    mine = store.read_json(store.tenant_file(), {}) or {}
    out = []
    for tenant in tenants():
        if tenant['id'] == here or tenant['status'] == 'suspended':
            continue
        data = tenant_data(tenant['id'])
        for account in (data.get('auth_users') or {}).values():
            theirs = account.get('identities') or {}
            # An OIDC subject is only unique at its issuer, and each tenant sets up its own.
            if any(theirs.get(p) == s and _issuer(mine, p) == _issuer(data, p) for p, s in links.items()):
                out.append({'id': tenant['id'], 'name': tenant['name'], 'url': tenant['url'],
                            'username': account.get('username')})
                break
    return out


def register_cli(app):
    import click
    from flask.cli import AppGroup

    group = AppGroup('tenants', help='The tenants of a hosted Floorbit.')

    @group.command('add')
    @click.argument('tenant_id')
    @click.option('--name', default='', help='The tenant\'s name, as people know it.')
    @click.option('--url', default='', help='Where its Floorbit answers, like https://tenant.example.com.')
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

    @group.command('agent-domain')
    @click.argument('domain', required=False)
    def agent_domain_cmd(domain):
        """Show or set the domain for the agents' Let's Encrypt certificates ("-" clears it)."""
        if domain is None:
            click.echo(agent_domain() or 'No domain: agents use Floorbit\'s own CA.')
            return
        try:
            found = set_agent_domain('' if domain == '-' else domain)
        except HostingError as exc:
            raise click.ClickException(str(exc)) from None
        click.echo(f'Agents get <tenant>.agent.{found} from Let\'s Encrypt.' if found
                   else 'Cleared: agents use Floorbit\'s own CA.')

    app.cli.add_command(group)

    admins = AppGroup('platform-admins', help='Who runs the platform: admins of the default tenant with the flag.')

    def _users():
        from auth.users import UserStore  # late: auth imports floorbit while it loads
        return UserStore(store.tenant_file)

    def _flag(username, on):
        from auth.users import UserError
        with store.using(tenant=_folder(store.DEFAULT_TENANT), event=''):
            try:
                _users().set_platform_admin(username, on)
            except UserError as exc:
                raise click.ClickException(str(exc)) from None

    @admins.command('add')
    @click.argument('username')
    def add_platform_admin(username):
        _flag(username, True)
        click.echo(f'{username} is a platform admin now.')

    @admins.command('remove')
    @click.argument('username')
    def remove_platform_admin(username):
        _flag(username, False)
        click.echo(f'{username} is no platform admin any more.')

    @admins.command('list')
    def list_platform_admins():
        with store.using(tenant=_folder(store.DEFAULT_TENANT), event=''):
            found = [u['username'] for u in _users().list() if u.get('platform_admin')]
        click.echo('\n'.join(found) if found else 'No platform admins.')

    app.cli.add_command(admins)
