"""Roles: named sets of permissions (RBAC). See docs/auth.md.

Every request needs one permission (``needed_for``), and an account's role says which ones it
has. Built-in roles can't be changed; admins add their own under Settings > Roles and teams.
Team roles (auth/teams.py) add permissions inside a team only.

Accounts from before roles existed have no role stored and count as admin, so nobody is locked
out by an upgrade; the old "editor" role is now "lead".
"""
import re
import threading

# Permission id -> what it allows, as the roles page shows it.
PERMISSIONS = {
    'floorplan.view': 'See the floor plan, dashboards and live switch status',
    'floorplan.edit': 'Change the floor plan and the inventory, run syncs',
    'seats.view': 'See who sits where: nicks, IPs, MACs and check-ins',
    'seats.edit': 'Change the seat mapping and check-ins',
    'incidents.work': 'Work incidents assigned to their teams',
    'incidents.assign': 'Assign incidents to any team',
    'ports.act': 'Run port actions and show commands on switches',
    'commands.change': 'Run switch commands that change something, such as clearing counters',
    'terminal.open': 'Open a terminal on a switch in the browser, with their own switch login',
    'configs.read': 'Back up switch configs and read them and what changed',
    'power.edit': 'Change power boards and circuits, enter readings and trips',
    'games.rcon': 'Send RCON commands to game servers',
    'plugins.run': 'Run plugin actions',
    'audit.read': 'Read the audit log',
    'settings.manage': 'Change settings, plugins and backups',
    'accounts.manage': 'Manage accounts, roles and teams',
}

BUILTIN = {
    'admin': {'label': 'Admin', 'description': 'Everything, including settings, accounts, plugins and roles.',
              'permissions': list(PERMISSIONS)},
    'lead': {'label': 'Lead',
             'description': 'Everything a tech can, plus the floor plan, assigning incidents to any team '
                            'and reading the audit log.',
             'permissions': ['floorplan.view', 'floorplan.edit', 'seats.view', 'seats.edit', 'incidents.work',
                             'incidents.assign', 'ports.act', 'commands.change', 'terminal.open', 'configs.read',
                             'power.edit', 'games.rcon', 'plugins.run', 'audit.read']},
    'tech': {'label': 'Tech',
             'description': 'Works incidents for their teams, runs port actions, sees seat and network data.',
             'permissions': ['floorplan.view', 'seats.view', 'incidents.work', 'ports.act', 'games.rcon']},
    'viewer': {'label': 'Viewer', 'description': 'Looks at the floor plan and dashboards, changes nothing.',
               'permissions': ['floorplan.view']},
    'kiosk': {'label': 'Kiosk', 'description': 'A read-only account for a big screen. Remove it to revoke it.',
              'permissions': ['floorplan.view']},
}
# Old role names still stored in data.json.
ALIASES = {'editor': 'lead'}
DEFAULT_ROLE = 'lead'
LEGACY_ROLE = 'admin'
ROLE_ID_RE = re.compile(r'^[a-z][a-z0-9-]{1,31}$')
KEY = 'auth_roles'

# Kept so older imports keep working; the full list is all_roles().
ROLES = tuple(BUILTIN)
LABELS = {k: v['label'] for k, v in BUILTIN.items()}

_lock = threading.Lock()
_path = None    # callable returning the data file (tests point it elsewhere)


class RoleError(ValueError):
    pass


def configure(path_getter):
    global _path
    _path = path_getter


# storage --------------------------------------------------------------------------------------
def _read():
    path = _path() if _path else None
    if not path:
        return {}
    from floorbit.store import read_json  # late: floorbit imports auth while it loads
    return read_json(path, {})


def _write(data):
    # In place, not via rename: data.json is bind-mounted in docker-compose.
    from floorbit.store import write_json
    write_json(_path(), data)


def _custom(data=None):
    raw = (data if data is not None else _read()).get(KEY) or {}
    return {k: v for k, v in raw.items() if isinstance(v, dict) and k not in BUILTIN}


def all_roles():
    """{id: {label, description, permissions, builtin}}: built-in first, then custom by label."""
    out = {k: {**v, 'builtin': True} for k, v in BUILTIN.items()}
    for k, v in sorted(_custom().items(), key=lambda kv: kv[1].get('label', kv[0]).lower()):
        out[k] = {'label': v.get('label') or k, 'description': v.get('description') or '',
                  'permissions': [p for p in v.get('permissions') or [] if p in PERMISSIONS], 'builtin': False}
    return out


def label(role):
    return all_roles().get(role, {}).get('label', role)


# checks ---------------------------------------------------------------------------------------
def validate(role):
    role = role.strip().lower() if isinstance(role, str) else ''
    role = ALIASES.get(role, role)
    if role not in all_roles():
        raise RoleError(f"Role must be one of: {', '.join(all_roles())}.")
    return role


def of(user):
    """The role of a user record (stored or public)."""
    role = (user or {}).get('role') or LEGACY_ROLE
    role = ALIASES.get(role, role)
    return role if role in all_roles() else 'viewer'


def permissions_of(role):
    return set(all_roles().get(ALIASES.get(role, role), {}).get('permissions') or [])


def can(user, permission):
    """Does this account (a user record or public user) have the permission everywhere?"""
    return permission in permissions_of(of(user))


# custom roles ---------------------------------------------------------------------------------
def _managers(data, roles_override):
    """How many accounts could still manage accounts with these role definitions."""
    def perms(role):
        role = ALIASES.get(role, role)
        if role in BUILTIN:
            return set(BUILTIN[role]['permissions'])
        return set((roles_override.get(role) or {}).get('permissions') or [])
    users = (data.get('auth_users') or {}).values()
    return sum(1 for u in users if 'accounts.manage' in perms(u.get('role') or LEGACY_ROLE))


def save(role_id, label_text, description='', permissions=()):
    role_id = (role_id or '').strip().lower()
    if role_id in BUILTIN or role_id in ALIASES:
        raise RoleError('Built-in roles cannot be changed. Make a new role instead.')
    if not ROLE_ID_RE.match(role_id):
        raise RoleError('A role ID is 2 to 32 lowercase letters, digits or dashes, starting with a letter.')
    unknown = [p for p in permissions if p not in PERMISSIONS]
    if unknown:
        raise RoleError(f"Unknown permission: {', '.join(map(str, unknown))}")
    label_text = (label_text or '').strip()[:40]
    if not label_text:
        raise RoleError('Give the role a name.')
    with _lock:
        data = _read()
        custom = _custom(data)
        custom[role_id] = {'label': label_text, 'description': (description or '').strip()[:200],
                           'permissions': [p for p in PERMISSIONS if p in set(permissions)]}
        if _managers(data, custom) == 0:
            raise RoleError('Then nobody could manage accounts any more. Keep "Manage accounts" on this role.')
        data[KEY] = custom
        _write(data)
    return custom[role_id]


def delete(role_id):
    if role_id in BUILTIN:
        raise RoleError('Built-in roles cannot be removed.')
    with _lock:
        data = _read()
        custom = _custom(data)
        if role_id not in custom:
            raise RoleError(f'No role called {role_id}.')
        users = [u['username'] for u in (data.get('auth_users') or {}).values()
                 if u.get('role') == role_id or role_id in (u.get('teams') or {}).values()]
        if users:
            raise RoleError(f"{len(users)} account(s) still have this role: {', '.join(sorted(users)[:5])}. "
                            'Give them another role first.')
        del custom[role_id]
        data[KEY] = custom
        _write(data)


# the request guard ----------------------------------------------------------------------------
READ = ('GET', 'HEAD', 'OPTIONS')
WRITE = ('POST', 'PUT', 'PATCH', 'DELETE')
# (path prefix, methods, permission), first match wins, so specific paths come first. A request
# no rule matches needs floorplan.view to read and an admin (settings.manage) to change anything:
# a new route is closed until someone gives it a rule here.
RULES = (
    # Everyone signed in keeps their own sidebar settings.
    ('/api/auth/me', None, 'floorplan.view'),
    # Which of the tenant's events this browser works on (floorbit/blueprints/tenant_events.py).
    ('/api/tenant/current', None, 'floorplan.view'),
    ('/api/settings/audit', READ, 'audit.read'),
    # The event changelog has the audit log in it, with who (floorbit/timeline.py).
    ('/api/timeline', READ, 'audit.read'),
    ('/api/timeline.csv', READ, 'audit.read'),
    ('/timeline', READ, 'audit.read'),
    ('/settings/audit', READ, 'audit.read'),
    ('/api/settings', None, 'settings.manage'),
    # Local agents (floorbit/agent_link.py): enrolling one hands out a key to the event's data.
    ('/api/agents', None, 'settings.manage'),
    # Clearing a failed agent login lets the agent try that password again (floorbit/agent_plugins.py).
    ('/api/agent-plugins', WRITE, 'plugins.run'),
    ('/settings/users', None, 'accounts.manage'),
    ('/settings/teams', None, 'accounts.manage'),
    ('/settings', None, 'settings.manage'),
    ('/api/users', None, 'accounts.manage'),
    ('/api/roles', None, 'accounts.manage'),
    ('/api/teams', None, 'accounts.manage'),
    ('/api/integrations', None, 'settings.manage'),
    ('/api/demo', None, 'settings.manage'),
    # Starting a new event clears the report's history; adding nicks and IPs is checked in the blueprint.
    ('/api/report/new-event', WRITE, 'settings.manage'),
    ('/api/cache/invalid', WRITE, 'floorplan.edit'),
    # Crew notes on a seat (floorbit/seat_notes.py); reading them is checked in the blueprint.
    ('/api/plan/seats', WRITE, 'incidents.work'),
    ('/api/switches', WRITE, 'floorplan.edit'),
    ('/api/links', WRITE, 'floorplan.edit'),
    ('/api/firewalls', WRITE, 'floorplan.edit'),
    ('/api/services', WRITE, 'floorplan.edit'),
    ('/api/seat-blocks', WRITE, 'floorplan.edit'),
    ('/api/plan-marks', WRITE, 'floorplan.edit'),
    ('/api/plan-groups', WRITE, 'floorplan.edit'),
    ('/api/plan-locks', WRITE, 'floorplan.edit'),
    ('/api/halls', WRITE, 'floorplan.edit'),
    ('/api/templates', WRITE, 'floorplan.edit'),
    ('/api/tournament', WRITE, 'floorplan.edit'),
    ('/api/inventory/log', READ, 'floorplan.edit'),
    ('/api/inventory', WRITE, 'floorplan.edit'),
    ('/api/seat-map', READ, 'seats.view'),
    ('/api/seat-map.csv', READ, 'seats.view'),
    ('/api/seat-map', WRITE, 'seats.edit'),
    ('/seat-mapping', READ, 'seats.view'),
    ('/api/checkins', READ, 'seats.view'),
    ('/api/checkins', WRITE, 'seats.edit'),
    ('/checkins', READ, 'seats.view'),
    # Nicks and IPs per seat, and what a seat's IP resolves to: personal data.
    ('/api/seats/info', READ, 'seats.view'),
    # Where each machine was seen: IPs and MACs by port and seat (floorbit/endpoints.py).
    ('/api/endpoints', READ, 'seats.view'),
    ('/endpoints', READ, 'seats.view'),
    ('/api/seats/find', READ, 'seats.view'),
    ('/api/plan/find', READ, 'seats.view'),
    ('/api/seats/sources', READ, 'seats.view'),
    ('/api/seats/resolve', WRITE, 'seats.view'),
    ('/api/resolve', READ, 'seats.view'),
    # Incidents: the blueprint checks incidents.work per team (floorbit/incidents.py).
    ('/api/helpdesk/qr', READ, 'incidents.assign'),
    ('/incidents/qr', READ, 'incidents.assign'),
    ('/api/incidents', WRITE, 'floorplan.view'),
    # Speed tests from the seats' help pages: the crew's, like the board (floorbit/speedtest.py).
    ('/api/speedtests', READ, 'incidents.work'),
    ('/speedtests', READ, 'incidents.work'),
    # Tech dispatch: the blueprint checks incidents.work, and incidents.assign for sending (floorbit/dispatch.py).
    ('/api/jobs', WRITE, 'floorplan.view'),
    ('/api/dispatch/auto', WRITE, 'incidents.assign'),   # automatic dispatch on or off (issue #358)
    ('/api/dispatch', READ, 'incidents.assign'),
    # Cables and patching: reading is floorplan.view, like the floor plan (floorbit/cables.py).
    # Which MAC and IP is on which seat port is personal data, like the seat mapping.
    ('/api/cables/clients', None, 'seats.view'),
    ('/api/cables', WRITE, 'floorplan.edit'),
    ('/api/cable-plan', WRITE, 'floorplan.edit'),
    # Which seats a range of ports roughly goes to: part of the patch plan (floorbit/port_areas.py).
    ('/api/port-areas/lookup', None, 'seats.view'),
    ('/api/port-areas', WRITE, 'floorplan.edit'),
    # Saved dashboard layouts: what a screen shows is the floor crew's to arrange (floorbit/dashboard_layouts.py).
    ('/api/dashboard/layouts', WRITE, 'floorplan.edit'),
    # Dashboards (floorbit/dashboards.py): arranged by the floor crew, like the older tile layouts.
    ('/api/dashboards', WRITE, 'floorplan.edit'),
    # Runbooks: the crew reads them, leads write them (floorbit/runbooks.py).
    ('/api/runbooks', READ, 'incidents.work'),
    ('/api/runbooks', WRITE, 'incidents.assign'),
    ('/runbooks', READ, 'incidents.work'),
    # Schedule: everyone reads it, leads plan it; /agenda itself is public (floorbit/schedule.py).
    ('/api/schedule', WRITE, 'floorplan.edit'),
    # Status page: the crew's view and updates; /status itself is public (floorbit/status_page.py).
    ('/api/status-page', READ, 'incidents.work'),
    ('/api/status-page', WRITE, 'incidents.assign'),
    ('/network-status', READ, 'incidents.work'),
    # Pre-flight checks ask the monitoring source and the health plugins now (floorbit/preflight.py).
    ('/api/preflight/run', WRITE, 'incidents.work'),
    # Past events: closing one clears the running event's history, and a backup is an admin's.
    ('/api/past-events/backup', READ, 'settings.manage'),
    ('/api/past-events', WRITE, 'settings.manage'),
    # Crew notice: everyone who sees the floor plan reads it, leads put it up (floorbit/notice.py).
    ('/api/notice', WRITE, 'incidents.assign'),
    # Shift handover: the crew's summary, with names from the audit log (floorbit/handover.py).
    ('/api/handover', None, 'incidents.work'),
    ('/handover', READ, 'incidents.work'),
    # Port actions: the switch login is the tech's own, typed for each action (floorbit/ports.py).
    ('/api/ports', None, 'ports.act'),
    # Switch commands: change templates also need commands.change, checked in the blueprint.
    ('/api/commands/templates', WRITE, 'settings.manage'),
    ('/api/commands', None, 'ports.act'),
    ('/commands', READ, 'ports.act'),
    # The browser terminal: every line typed is audited (floorbit/terminal.py).
    ('/api/terminal', None, 'terminal.open'),
    # Game servers (floorbit/game_servers.py): the crew asks and sends RCON, admins set them up.
    ('/api/game-servers/rcon', WRITE, 'games.rcon'),
    ('/api/game-servers/check', WRITE, 'games.rcon'),
    ('/api/game-servers', WRITE, 'settings.manage'),
    ('/terminal', READ, 'terminal.open'),
    # Switch configs describe the whole network, even with the secrets taken out (floorbit/config_backup.py).
    ('/api/configs', None, 'configs.read'),
    ('/configs', READ, 'configs.read'),
    # Security findings name MACs and IPs; asking the plugins now is like running a plugin action.
    ('/api/security/check', WRITE, 'plugins.run'),
    ('/api/security', None, 'seats.view'),
    ('/security', READ, 'seats.view'),
    ('/api/logs', None, 'seats.view'),   # logs name MACs and IPs
    ('/logs', READ, 'seats.view'),
    # Asking every health plugin now sends requests out: the same as running a plugin action.
    ('/api/health', WRITE, 'plugins.run'),
    # Power: changes need power.edit, readings and trips also incidents.work in the Electrics team;
    # the blueprint checks that (floorbit/blueprints/power.py). Asking the meters is a plugin run.
    ('/api/power/check', WRITE, 'plugins.run'),
    # Muting a switch's alerts is for the people working the problems.
    ('/api/alerts', WRITE, 'incidents.work'),
    ('/api/power', WRITE, 'floorplan.view'),
    # Plugin actions check the permission each action names (floorbit/blueprints/plugins.py).
    ('/api/plugins', WRITE, 'floorplan.view'),
)


def needed_for(path, method, safe_methods=READ):
    """The permission this request needs."""
    reading = method in safe_methods
    for prefix, methods, permission in RULES:
        if (path == prefix or path.startswith(prefix + '/')) and (
                methods is None or (reading and methods is READ) or (not reading and methods is WRITE)):
            return permission
    return 'floorplan.view' if reading else 'settings.manage'
