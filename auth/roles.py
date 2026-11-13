"""Roles: what a signed-in account may do.

- viewer: open the floor plan editor read-only, change nothing.
- editor: change the floor plan (switches, seat blocks, cache, sync).
- admin:  everything, including /settings and managing accounts.

Each role includes the ones below it. Accounts from before roles existed have
no role stored and count as admin, so nobody is locked out by the upgrade.
"""

ROLES = ('viewer', 'editor', 'admin')
LABELS = {
    'viewer': 'Viewer',
    'editor': 'Editor',
    'admin': 'Admin',
}
DESCRIPTIONS = {
    'viewer': 'Can look at the floor plan, cannot change anything.',
    'editor': 'Can place and edit switches and seat blocks.',
    'admin': 'Can also change settings and manage accounts.',
}
DEFAULT_ROLE = 'editor'
LEGACY_ROLE = 'admin'

# Paths below these need an admin, whatever the method.
ADMIN_PATHS = ('/settings', '/api/settings', '/api/users')


class RoleError(ValueError):
    pass


def validate(role):
    role = (role or '').strip().lower()
    if role not in ROLES:
        raise RoleError(f"Role must be one of: {', '.join(ROLES)}.")
    return role


def of(user):
    """The role of a user record (stored or public)."""
    role = (user or {}).get('role') or LEGACY_ROLE
    return role if role in ROLES else 'viewer'


def allows(role, needed):
    return ROLES.index(role) >= ROLES.index(needed)


def needed_for(path, method, safe_methods):
    """The lowest role that may make this request."""
    if any(path == p or path.startswith(p + '/') for p in ADMIN_PATHS):
        return 'admin'
    if method not in safe_methods:
        return 'editor'
    return 'viewer'
