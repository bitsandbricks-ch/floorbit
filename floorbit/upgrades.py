"""Moving stored data to its current shape, once (one code path for old and new installs).

Older Floorbits saved some parts of data.json differently. Instead of every reader still knowing
each old shape, the steps in ``STEPS`` move a document up once and ``data_version`` records how far
it got. After that, the code reads one shape only.

- ``apply`` runs the missing steps on a loaded document, in place; ``store.load_data`` calls it, so
  any event's or tenant's document is current before anyone reads it. It is a no-op when the
  document is up to date.
- ``run_at_start`` brings the current event and its tenant up to date and saves them when Floorbit
  starts, so readers that go straight to the file (accounts, ``store.read_shared``) see the
  current shape too.
- A restored backup goes through ``apply`` before it is checked (floorbit/blueprints/backup.py).

Add a step at the end; never change or remove one that has shipped (a document that already ran
it would not run the new version). Steps must be safe to run twice: a later event's document runs
them over the tenant's parts, which the first event already moved.
"""
import uuid

KEY = 'data_version'


# ── the steps ────────────────────────────────────────────────────────────────────────────────

def _inventory(data):
    """The switch lists from before the inventory (``switches``, ``cached_devices``,
    ``positions``) become ``inventory``."""
    from . import inventory
    if isinstance(data.get('inventory'), list):
        for key in ('switches', 'cached_devices', 'positions'):
            data.pop(key, None)
        return
    devices = []
    for s in data.get('switches') or []:
        if not isinstance(s, dict) or not s.get('id'):
            continue
        placed = s.get('placed', True) and s.get('x') is not None
        devices.append(inventory.blank(id=str(s['id']), name=str(s.get('name') or 'Switch')[:80],
                                       x=s.get('x') if placed else None, y=s.get('y') if placed else None))
    positions = data.get('positions') or {}
    for d in data.get('cached_devices') or []:
        if not isinstance(d, dict) or not d.get('id'):
            continue
        did = str(d['id'])
        pos = positions.get(did) or {}
        status = str(d.get('netbox_status') or '')
        devices.append(inventory.blank(id=did, name=str(d.get('name') or did)[:80], status=status,
                                       x=pos.get('x'), y=pos.get('y'), origin='netbox', refs={'netbox': did},
                                       fed={'netbox': {'name': d.get('name') or did, 'status': status}}))
    data['inventory'] = devices
    for key in ('switches', 'cached_devices', 'positions'):
        data.pop(key, None)


def _display_settings(data):
    """The first settings page's ``default_settings`` ({hide_labels, exclude_heatmap}) become
    ``app_settings`` entries. A value saved since wins."""
    old = data.pop('default_settings', None)
    if not isinstance(old, dict):
        return
    stored = data.get('app_settings') if isinstance(data.get('app_settings'), dict) else {}
    for was, now in (('hide_labels', 'display.hide_labels'), ('exclude_heatmap', 'display.exclude_heatmap')):
        if was in old and now not in stored:
            stored[now] = bool(old[was])
    if stored:
        data['app_settings'] = stored


ROLE_RENAMED = {'editor': 'lead'}
ROLE_BEFORE_ROLES = 'admin'      # accounts and tokens from before roles could do everything


def _roles(data):
    """Accounts and API tokens from before roles get ``admin`` (what they could do); the old role
    name ``editor`` is ``lead`` everywhere it is stored."""
    def renamed(role):
        return ROLE_RENAMED.get(role, role)

    for key in ('auth_users', 'api_tokens'):
        for record in (data.get(key) or {}).values() if isinstance(data.get(key), dict) else ():
            if not isinstance(record, dict):
                continue
            record['role'] = renamed(record.get('role') or ROLE_BEFORE_ROLES)
            if isinstance(record.get('teams'), dict):
                record['teams'] = {tid: renamed(role) for tid, role in record['teams'].items()}
    oidc = data.get('auth_oidc')
    for provider in oidc.values() if isinstance(oidc, dict) else ():
        for rule in (provider.get('role_mapping') or []) if isinstance(provider, dict) else ():
            if isinstance(rule, dict) and rule.get('role'):
                rule['role'] = renamed(rule['role'])


def _block_groups(data):
    """The classic editor's seat block ``group`` field becomes a plan group (floorbit/plan_groups.py)
    per hall, for groups of at least two blocks that aren't in a plan group already."""
    from . import halls, plan_groups
    blocks = [b for b in data.get('seat_blocks') or [] if isinstance(b, dict)]
    grouped = {(m.get('kind'), m.get('id')) for g in data.get(plan_groups.KEY) or [] if isinstance(g, dict)
               for m in g.get('members') or [] if isinstance(m, dict)}
    found = {}
    for b in blocks:
        group = str(b.pop('group', None) or '').strip()
        if group and b.get('id') and ('block', b['id']) not in grouped:
            found.setdefault((halls.hall_of(b, data), group), []).append(b['id'])
    for (hall_id, name), ids in found.items():
        if len(ids) >= 2:
            data.setdefault(plan_groups.KEY, []).append({
                'id': uuid.uuid4().hex[:12], 'hall_id': hall_id, 'name': name[:plan_groups.NAME_MAX],
                'members': [{'kind': 'block', 'id': i} for i in ids[:plan_groups.MAX_MEMBERS]]})


def _dashboards(data):
    """Dashboards saved as one split tree (``root``) become a grid with that tree filling it."""
    from . import dashboards
    raw = data.get(dashboards.KEY)
    if isinstance(raw, list):
        data[dashboards.KEY] = [dashboards.upgrade(x) if isinstance(x, dict) else x for x in raw]


def _switch_logins(data):
    """Settings > Switch logins (``credentials``, by name pattern) become the inventory's SSH
    credentials: ``*`` goes on the defaults, one switch's name on that device, and a pattern on a tag
    of that name, given to every device it matches now. Where the inventory already has an SSH
    credential at that place, that one stays. A login whose password won't open (the key is gone)
    is dropped with a note in the log: it has to be set again."""
    import fnmatch

    from . import inventory, inventory_scope, vault
    old = [c for c in data.pop('credentials', None) or [] if isinstance(c, dict) and c.get('kind') == 'ssh'
           and c.get('scope') and c.get('username') and c.get('password')]
    if not old:
        return
    creds = data.setdefault(inventory_scope.CREDS, [])
    taken = {(c.get('owner_type'), c.get('owner_id')) for c in creds if isinstance(c, dict) and c.get('kind') == 'ssh'}
    devices = inventory.devices(data, include_hidden=True)

    def names(dev):
        name = str(dev.get('name') or '').lower()
        return name, name.split('.')[0]

    for entry in old:
        scope = str(entry['scope'])
        try:
            password = vault.open_(f"ssh:{entry['id']}", entry['password'])
        except vault.VaultError as exc:
            print(f"[upgrades] The switch login for {scope} could not be opened ({exc}); set it again "
                  'in the inventory.', flush=True)
            continue
        if scope == '*':
            owner = ('defaults', 'defaults')
        elif '*' not in scope and '?' not in scope and (dev := next(
                (d for d in devices if scope.lower() in names(d)), None)) is not None:
            owner = ('device', dev['id'])
        else:
            tags = data.setdefault(inventory_scope.TAGS, [])
            tag = next((t for t in tags if str(t.get('name', '')).lower() == scope.lower()), None)
            if tag is None:
                tag = {'id': uuid.uuid4().hex[:12], 'name': scope[:60], 'icon': '', 'color': '', 'properties': {},
                       'features': {}, 'description': f'The switch login for {scope}, from Settings > Switch logins.'}
                tags.append(tag)
            pattern = scope.lower()
            for dev in devices:
                has = dev.get('tags') or []
                if any(fnmatch.fnmatchcase(n, pattern) for n in names(dev)) and tag['id'] not in has:
                    dev['tags'] = [*(dev.get('tags') or []), tag['id']]
            owner = ('tag', tag['id'])
        if owner in taken:
            continue
        taken.add(owner)
        cred = {'id': uuid.uuid4().hex[:12], 'kind': 'ssh', 'owner_type': owner[0], 'owner_id': owner[1],
                'username': entry['username'], 'rev': uuid.uuid4().hex[:10],
                'set_at': entry.get('set_at'), 'set_by': entry.get('set_by')}
        cred['secrets'] = {'secret': vault.seal(inventory_scope._slot(cred, 'secret'), password)}
        creds.append(cred)


def _no_brackets(data):
    """Tournament brackets were removed (an operations tool doesn't run the tournament): their
    data and their public page's switch go."""
    data.pop('brackets', None)
    if isinstance(data.get('app_settings'), dict):
        data['app_settings'].pop('public.brackets', None)


def _no_runbooks(data):
    """Runbooks were removed (fix guides live with the crew's own notes): their data and their
    feature switch go."""
    data.pop('runbooks', None)
    if isinstance(data.get('features'), dict):
        data['features'].pop('runbooks', None)


def _no_seat_finder(data):
    """The "find your seat" page was removed: its saved switches go."""
    if isinstance(data.get('app_settings'), dict):
        for key in ('integrations.seat_finder', 'integrations.seat_finder_nicks'):
            data['app_settings'].pop(key, None)


def _small_status_page(data):
    """The status page lost planned maintenance and the switch-names option, and the attendee view
    (``/hall``) went: drop what they kept."""
    page = data.get('status_page')
    if isinstance(page, dict):
        page.pop('planned', None)
    settings = data.get('app_settings')
    if isinstance(settings, dict):
        for key in ('public.attendee_view', 'public.status_switch_names'):
            settings.pop(key, None)
    features = data.get('features')
    if isinstance(features, dict):
        features.pop('public_hall', None)


def _no_attendee_programme(data):
    """The public agenda (/agenda) and the attendee Discord channels went: their settings go. The crew's
    schedule stays."""
    if isinstance(data.get('app_settings'), dict):
        for key in ('public.schedule', 'integrations.discord_status_webhook_url',
                    'integrations.discord_schedule_webhook_url', 'integrations.schedule_announce_minutes'):
            data['app_settings'].pop(key, None)


def _platform_admins(data):
    """Platform admins became a flag of their own (auth/users.py): before, every admin of the default
    tenant was one. They keep it, so nobody loses the Tenants page; take it away on the Users page.
    Only in the default tenant: other tenants' admins never ran the platform."""
    from auth import roles  # late: auth imports floorbit while it loads

    from . import store
    users = data.get('auth_users')
    if store.tenant_dir() != '' or not isinstance(users, dict):
        return
    if any(isinstance(u, dict) and u.get('platform_admin') for u in users.values()):
        return
    for user in users.values():
        if isinstance(user, dict) and 'settings.manage' in roles.permissions_of(roles.of(user)):
            user['platform_admin'] = True


STEPS = (_inventory, _display_settings, _roles, _block_groups, _dashboards, _switch_logins, _no_brackets,
         _no_runbooks, _no_seat_finder, _small_status_page, _no_attendee_programme,
         _platform_admins)
CURRENT = len(STEPS)


def current(data):
    return isinstance(data, dict) and data.get(KEY) == CURRENT


def apply(data):
    """Run the steps ``data`` hasn't had, in place. Returns True when it changed."""
    if not isinstance(data, dict):
        return False
    done = data.get(KEY)
    done = done if isinstance(done, int) and not isinstance(done, bool) and 0 <= done <= CURRENT else 0
    if done == CURRENT:
        return False
    for step in STEPS[done:]:
        step(data)
    data[KEY] = CURRENT
    return True


def upgrade_layout(layout):
    """A backup's floor plan parts (floorbit/blueprints/backup.py), moved like data.json's. A backup
    names no ``data_version``, so the steps that touch those parts run; they're safe to run twice."""
    _inventory(layout)
    _block_groups(layout)


def run_at_start(log=print):
    """Bring the current event's document and its tenant's up to date, and save them."""
    from . import store
    data = store.load_data()          # applies the steps
    if getattr(data, '_upgraded', False):
        store.save_data(data)
        log(f'[upgrades] Stored data moved to its current shape (version {CURRENT}).')
