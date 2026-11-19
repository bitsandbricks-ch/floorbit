"""Every page a crew member may want to jump to, for "Go to" (Ctrl+K) on every page (issues #242, #250).

One list on the server, so the React pages, the floor plan and Settings offer the same pages, and the
conditions match what the floor plan offers: the features that are on, the
account's permissions, and what this server has set up (a Wi-Fi source, power boards, ...).
The server still checks every page; this only keeps the list honest.
"""
import re
from urllib.parse import quote

from . import incidents, inventory, store
from .store import load_data

# (href, id, English label, needs): ``needs`` maps the page's template context and a ``can``
# function to True when the page belongs in the list. ``id`` names its texts in the React app
# (frontend/src/i18n/*/goto.json).
PAGES = (
    ('/overview', 'overview', 'Overview', None),
    ('/plan', 'floorPlan', 'Floor plan', None),
    ('/dashboards', 'dashboards', 'Dashboards', None),
    ('/widgets', 'widgets', 'Widgets', None),
    ('/problems', 'problems', 'Problems', None),
    ('/incidents', 'incidents', 'Incidents',
     lambda c, can: c['feature_on']('incidents') and c.get('incidents_board')),
    ('/jobs', 'jobs', 'My jobs', lambda c, can: c['feature_on']('dispatch') and can('incidents.work')),
    ('/handover', 'handover', 'Shift handover', lambda c, can: c['feature_on']('handover') and can('incidents.work')),
    ('/topology', 'topology', 'Topology', None),
    ('/firewalls', 'firewalls', 'Firewalls', None),
    ('/services', 'services', 'Services', None),
    ('/logs', 'logs', 'Logs',
     lambda c, can: c['feature_on']('syslog') and c.get('logs_page') and can('seats.view')),
    ('/security', 'security', 'Security', lambda c, can: c['feature_on']('security') and can('seats.view')),
    ('/endpoints', 'endpoints', 'IP and MAC history', lambda c, can: can('seats.view')),
    ('/power', 'power', 'Electrics', lambda c, can: c['feature_on']('power') and c.get('power_on')),
    ('/commands', 'commands', 'Switch commands',
     lambda c, can: c['feature_on']('commands') and c.get('commands_on') and can('ports.act')),
    ('/terminal', 'terminal', 'Switch terminal', lambda c, can: c['feature_on']('terminal') and can('terminal.open')),
    ('/inventory', 'inventory', 'Inventory', None),
    ('/seat-mapping', 'seatMapping', 'Seat mapping', lambda c, can: can('seats.view')),
    ('/cables', 'cables', 'Cables', lambda c, can: c['feature_on']('cables')),
    ('/checkins', 'checkins', 'Check-in', lambda c, can: can('seats.view') and _checkin_on()),
    ('/seat-walk', 'seatWalk', 'Seat walk-through', lambda c, can: can('seats.edit')),
    ('/switch-areas', 'switchAreas', 'Switch areas', lambda c, can: can('seats.view')),
    ('/preflight', 'preflight', 'Pre-flight check', lambda c, can: c['feature_on']('preflight')),
    ('/schedule', 'schedule', 'Schedule', lambda c, can: c['feature_on']('schedule')),
    ('/timeline', 'timeline', 'Event changelog', lambda c, can: c['feature_on']('timeline') and can('audit.read')),
    ('/telemetry', 'telemetry', 'Telemetry', None),
    ('/network-status', 'networkStatus', 'Network status',
     lambda c, can: c['feature_on']('status_page') and can('incidents.work')),
    ('/replay', 'replay', 'Event replay', lambda c, can: c['feature_on']('replay')),
    ('/report', 'report', 'Event report', lambda c, can: c['feature_on']('report')),
    ('/events', 'events', 'Past events', lambda c, can: c['feature_on']('past_events')),
    ('/templates', 'templates', 'Floor plan templates', None),
    ('/settings', 'settings', 'Settings', lambda c, can: can('settings.manage')),
    ('/settings/plugins', 'plugins', 'Plugins', lambda c, can: can('settings.manage')),
    ('/settings/features', 'features', 'Features', lambda c, can: can('settings.manage')),
    ('/settings/sidebar', 'sidebarSections', 'Sidebar sections', lambda c, can: can('settings.manage')),
    ('/settings/api', 'apiTokens', 'API tokens', lambda c, can: can('settings.manage')),
    ('/settings/tenants', 'tenants', 'Tenants',
     lambda c, can: can('settings.manage') and store.current_tenant() == store.DEFAULT_TENANT
     and bool((c.get('current_user') or {}).get('platform_admin'))),
    ('/settings/agents', 'agents', 'Local agents', lambda c, can: can('settings.manage')),
    ('/settings/webhooks', 'webhooks', 'Webhooks', lambda c, can: can('settings.manage')),
    ('/settings/users', 'users', 'Users', lambda c, can: can('accounts.manage')),
    ('/settings/teams', 'teams', 'Roles and teams', lambda c, can: can('accounts.manage')),
    ('/settings/sign-in', 'signIn', 'Sign-in providers', lambda c, can: can('settings.manage')),
    ('/settings/audit', 'audit', 'Audit log', lambda c, can: can('audit.read')),
)


def _checkin_on():
    from integrations import config
    return config.get_bool('CHECKIN_ENABLED', False)


def for_context(ctx):
    """The pages for the template context of this request (``app.update_template_context``)."""
    user = ctx.get('current_user')
    perms = set((user or {}).get('permissions') or ())

    def can(permission):
        # Sign-in off: everyone may do everything, like the request guard.
        return not ctx.get('auth_enabled') or permission in perms

    return [{'href': href, 'id': page_id, 'label': label}
            for href, page_id, label, needs in PAGES if needs is None or needs(ctx, can)]


def _seat_key(seat):
    # B-8 before B-10: letters as text, numbers as numbers.
    return [(0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.split(r'(\d+)', seat)]


def _squash(text):
    return re.sub(r'[\s\-_.]', '', str(text or '')).lower()


def places(query, data=None, limit=5):
    """Seats and switches for "Go to" (issue #252): "b8" finds seat B-8, "core" the switch core-01.

    Seat numbers and switch names only, which every crew role sees on the floor plan anyway; the
    route adds players by nick, IP or MAC only for ``seats.view`` (issue #292)."""
    q = _squash(query)
    if len(q) < 2:
        return []
    data = data if data is not None else load_data()
    seats = sorted(incidents.seat_numbers(data), key=_seat_key)
    hits = [s for s in seats if _squash(s) == q] + [s for s in seats if _squash(s).startswith(q) and _squash(s) != q]
    out = [{'kind': 'seat', 'name': s, 'href': f'/plan?seat={quote(s)}'} for s in hits[:limit]]
    names = sorted({str(d.get('name')) for d in inventory.devices(data) if d.get('name')}, key=_seat_key)
    matches = [n for n in names if q in _squash(n)]
    matches.sort(key=lambda n: not _squash(n).startswith(q))
    out += [{'kind': 'switch', 'name': n, 'href': f'/plan?switch={quote(n)}'} for n in matches[:limit]]
    return out
