"""Moving between a platform's tenants without signing in again (docs/tenancy.md).

Each tenant runs in its own processes at its own address, so a session can't cross over. Instead
the tenant you leave writes a hand-off into the tenant you go to: a one-time ticket, good for
``TICKET_TTL`` seconds, that the browser carries over in the address. The other side takes it
(deleting it, so it works once) and signs the browser in there.

Two kinds of ticket:

- ``account``: the person has an account there too, linked by the same outside login
  (``hosting.memberships``). They arrive as that account.
- ``platform``: an admin of the default tenant opens a tenant where they have no account. They
  arrive as ``platform:<name>``, an admin visitor that exists only in the session, for at most
  ``VISIT_HOURS``. Every request checks that they are still an admin of the default tenant, and the
  visit is in the tenant's audit log, so its own admins see who came in.
"""
import hashlib
import os
import secrets
import time

from . import hosting, store

TICKET_TTL = 60
VISIT_HOURS = 8
PLATFORM_PREFIX = 'platform:'
FOLDER = 'handoffs'
_TICKET_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_')


class SwitchError(ValueError):
    pass


def _ticket_path(ticket):
    # Stored under its hash: whoever can read the storage still can't use a waiting ticket.
    return store.tenant_path(FOLDER, hashlib.sha256(ticket.encode()).hexdigest() + '.json')


def _sweep(now):
    folder = store.tenant_path(FOLDER)
    for name in store.list_json(folder):
        doc = store.read_json(os.path.join(folder, name), {}) or {}
        if not isinstance(doc.get('until'), (int, float)) or doc['until'] < now:
            store.delete_json(os.path.join(folder, name))


def _platform_record(username):
    """The default tenant's account of a platform admin, or None when they no longer are one."""
    from auth import roles  # late: auth imports floorbit while it loads
    with store.using(tenant=store.tenant_folder(store.DEFAULT_TENANT), event=''):
        data = store.read_shared(store.tenant_file(), {}) or {}
    record = (data.get('auth_users') or {}).get(username)
    if not isinstance(record, dict) or not roles.can(record, 'settings.manage'):
        return None
    return record


def is_platform_admin(user):
    """Whether this signed-in account (a public record) may open every tenant: an admin here, on the
    default tenant. A visitor from the platform doesn't count: they can't hop on from there."""
    from auth import roles
    return bool(user and not user.get('api_token') and not user.get('platform')
                and store.current_tenant() == store.DEFAULT_TENANT
                and roles.can(user, 'settings.manage'))


def reachable(user, record):
    """The other tenants this person can switch to: ``[{id, name, url, how}]``, ``how`` being
    ``account`` or ``platform``. Only tenants with an address count: there is nowhere to send them
    otherwise."""
    if not user or user.get('api_token') or user.get('platform') or not hosting.several():
        return []
    out = {t['id']: {**{k: t[k] for k in ('id', 'name', 'url')}, 'how': 'account'}
           for t in hosting.memberships(record) if t.get('url')}
    if is_platform_admin(user):
        here = store.current_tenant()
        for t in hosting.tenants():
            if t['id'] != here and t['status'] == 'active' and t['url'] and t['id'] not in out:
                out[t['id']] = {**{k: t[k] for k in ('id', 'name', 'url')}, 'how': 'platform'}
    order = {t['id']: i for i, t in enumerate(hosting.tenants())}
    return sorted(out.values(), key=lambda t: order.get(t['id'], 0))


def issue(user, record, tenant_id, now=None):
    """Write a ticket into ``tenant_id`` for this person; the address to send the browser to."""
    now = time.time() if now is None else now
    target = next((t for t in reachable(user, record) if t['id'] == tenant_id), None)
    if not target:
        raise SwitchError('You have no way into that club.')
    ticket = secrets.token_urlsafe(32)
    if target['how'] == 'account':
        linked = next(t for t in hosting.memberships(record) if t['id'] == tenant_id)
        doc = {'how': 'account', 'username': linked['username'],
               'identities': {p: s for p, s in (record.get('identities') or {}).items() if s}}
    else:
        doc = {'how': 'platform', 'username': user['username'],
               'name': user.get('display_name') or user['username']}
    doc.update({'from': store.current_tenant(), 'until': now + TICKET_TTL})
    with store.using(tenant=store.tenant_folder(tenant_id), event=''):
        _sweep(now)
        store.write_json(_ticket_path(ticket), doc)
    return f"{target['url']}/switch/arrive?ticket={ticket}"


def take(ticket, now=None):
    """Use up a ticket written for the tenant this process serves; its hand-off, or None."""
    now = time.time() if now is None else now
    if not isinstance(ticket, str) or not 20 <= len(ticket) <= 100 or not set(ticket) <= _TICKET_CHARS:
        return None
    where = _ticket_path(ticket)
    doc = store.read_json(where, None)
    # Deleting is the claim: of two browsers with one ticket, only the one whose delete found it gets in.
    if not isinstance(doc, dict) or not store.delete_json(where):
        return None
    if not isinstance(doc.get('until'), (int, float)) or doc['until'] < now:
        return None
    return doc


def visitor(username, name, version):
    """The account record of a platform admin visiting this tenant, built for the session."""
    return {'username': PLATFORM_PREFIX + username, 'display_name': name or username, 'role': 'admin',
            'created_by': 'platform', 'session_version': version}


def visit_still_good(session):
    """For a visitor's session: their record, or None when the visit ended or they lost the right."""
    username = str(session.get('platform') or '')
    until = session.get('until')
    if not username or not isinstance(until, (int, float)) or until < time.time():
        return None
    record = _platform_record(username)
    if not record or record.get('session_version', 1) != session.get('ver'):
        return None
    return visitor(username, record.get('display_name'), record.get('session_version', 1))
