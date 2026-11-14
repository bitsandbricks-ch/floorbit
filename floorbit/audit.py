"""Audit log: who changed what, and when.

Every successful change through the API (floor plan, settings, accounts, a restored backup) and
every sign-in is appended as one JSON line to ``audit.jsonl`` next to ``data.json`` (or ``AUDIT_FILE``). Entries name
the account, the action and its target (a switch name, a seat block label, a username) and which
fields changed, never the values: settings hold tokens, and the floor plan's history is in the
backups. Settings > Audit log shows it; see docs/audit.md.
"""
import json
import os
import threading
import time

from flask import g, request, session

from . import store

MAX_BYTES = 2 * 1024 * 1024   # past this, the oldest half is dropped
_lock = threading.Lock()

# (method, URL rule) -> (area, action). Requests not listed here aren't logged: reads, the
# attendee check-in (it has its own history), lookups sent as POST, connection tests.
ACTIONS = {
    ('POST', '/api/switches'): ('floor plan', 'Added switch'),
    ('PUT', '/api/switches/<switch_id>'): ('floor plan', 'Changed switch'),
    ('DELETE', '/api/switches/<switch_id>'): ('floor plan', 'Deleted switch'),
    ('POST', '/api/switches/sync'): ('inventory', 'Synced the inventory'),
    ('POST', '/api/inventory'): ('inventory', 'Added device'),
    ('PATCH', '/api/inventory/<device_id>'): ('inventory', 'Changed device'),
    ('DELETE', '/api/inventory/<device_id>'): ('inventory', 'Removed device'),
    ('POST', '/api/inventory/sync'): ('inventory', 'Synced the inventory'),
    ('PUT', '/api/seat-map/<seat>'): ('seat mapping', 'Changed seat mapping'),
    ('DELETE', '/api/seat-map/<seat>'): ('seat mapping', 'Removed seat mapping'),
    ('POST', '/api/seat-map/import'): ('seat mapping', 'Imported seat mapping'),
    ('POST', '/api/seat-blocks'): ('floor plan', 'Added seat block'),
    ('PUT', '/api/seat-blocks/<block_id>'): ('floor plan', 'Changed seat block'),
    ('DELETE', '/api/seat-blocks/<block_id>'): ('floor plan', 'Deleted seat block'),
    ('POST', '/api/halls'): ('floor plan', 'Added hall'),
    ('PUT', '/api/halls/<hall_id>'): ('floor plan', 'Renamed hall'),
    ('DELETE', '/api/halls/<hall_id>'): ('floor plan', 'Deleted hall'),
    ('PUT', '/api/halls/<hall_id>/background'): ('floor plan', 'Set hall background'),
    ('DELETE', '/api/halls/<hall_id>/background'): ('floor plan', 'Removed hall background'),
    ('POST', '/api/halls/<hall_id>/seat-blocks.csv'): ('floor plan', 'Imported seat blocks'),
    ('POST', '/api/templates'): ('floor plan', 'Saved floor plan as template'),
    ('PATCH', '/api/templates/<template_id>'): ('floor plan', 'Changed template'),
    ('DELETE', '/api/templates/<template_id>'): ('floor plan', 'Deleted template'),
    ('POST', '/api/templates/<template_id>/versions'): ('floor plan', 'Saved a new template version'),
    ('POST', '/api/templates/<template_id>/duplicate'): ('floor plan', 'Duplicated template'),
    ('POST', '/api/templates/import'): ('floor plan', 'Imported template'),
    ('POST', '/api/templates/<template_id>/apply'): ('floor plan', 'Started from template'),
    ('PUT', '/api/settings'): ('settings', 'Changed settings'),
    ('PATCH', '/api/settings'): ('settings', 'Changed settings'),
    ('POST', '/api/settings/backup'): ('settings', 'Restored a backup'),
    ('POST', '/api/cache/invalid'): ('settings', 'Cleared the cache'),
    ('POST', '/api/integrations/discord/test'): ('settings', 'Sent a Discord test message'),
    ('POST', '/api/users'): ('accounts', 'Added account'),
    ('PATCH', '/api/users/<username>'): ('accounts', 'Changed account'),
    ('DELETE', '/api/users/<username>'): ('accounts', 'Deleted account'),
    ('PUT', '/api/roles/<role_id>'): ('accounts', 'Saved role'),
    ('DELETE', '/api/roles/<role_id>'): ('accounts', 'Deleted role'),
    ('POST', '/api/teams'): ('accounts', 'Added team'),
    ('PATCH', '/api/teams/<team_id>'): ('accounts', 'Changed team'),
    ('DELETE', '/api/teams/<team_id>'): ('accounts', 'Deleted team'),
    ('PUT', '/api/teams/<team_id>/members/<username>'): ('accounts', 'Changed team member'),
    ('DELETE', '/api/teams/<team_id>/members/<username>'): ('accounts', 'Removed team member'),
    ('DELETE', '/api/checkins/<seat>'): ('check-in', 'Removed check-in'),
    ('POST', '/api/checkins/refresh'): ('check-in', 'Refreshed check-ins'),
    ('PUT', '/api/settings/plugins/<plugin_id>'): ('plugins', 'Changed plugin'),
    ('PUT', '/api/settings/oidc/<provider_id>'): ('settings', 'Saved sign-in provider'),
    ('POST', '/api/incidents'): ('incidents', 'Filed incident'),
    ('PATCH', '/api/incidents/<incident_id>'): ('incidents', 'Changed incident'),
    ('DELETE', '/api/settings/oidc/<provider_id>'): ('settings', 'Removed sign-in provider'),
    ('POST', '/api/stats/peak/reset'): ('settings', 'Reset the bandwidth peak'),
}
AREAS = ('floor plan', 'inventory', 'seat mapping', 'settings', 'accounts', 'check-in', 'sign-in', 'plugins',
         'incidents', 'ports', 'security', 'power', 'alerts')
# Called with each logged change (not sign-ins): plugins hook in here, see floorbit/plugins.
listeners = []


def path():
    # Compose bind-mounts only data.json itself, so it points AUDIT_FILE into the state volume.
    return os.environ.get('AUDIT_FILE') or os.path.join(
        os.path.dirname(os.path.abspath(store.DATA_FILE)), 'audit.jsonl')


def record(area, action, user=None, target=None, fields=None, ok=True):
    entry = {
        'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'user': user,
        'area': area,
        'action': action,
    }
    if target:
        entry['target'] = str(target)[:120]
    if fields:
        entry['fields'] = sorted(str(f) for f in fields)[:40]   # names only, never values
    if not ok:
        entry['ok'] = False
    line = json.dumps(entry, separators=(',', ':')) + '\n'
    with _lock:
        try:
            with open(path(), 'a', encoding='utf-8') as f:
                f.write(line)
            _trim()
        except OSError as exc:   # a full disk must not break the change itself
            print(f'[audit] could not write the audit log: {exc}')
    return entry


def _trim():
    p = path()
    if os.path.getsize(p) <= MAX_BYTES:
        return
    with open(p, encoding='utf-8') as f:
        lines = f.readlines()
    with open(p, 'w', encoding='utf-8') as f:
        f.writelines(lines[len(lines) // 2:])


def read(limit=100, offset=0, user=None, area=None, query=None):
    """Newest first, filtered. Returns (entries, total matching)."""
    try:
        with open(path(), encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        return [], 0
    rows = []
    q = (query or '').strip().lower()
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if user and (e.get('user') or '') != user:
            continue
        if area and e.get('area') != area:
            continue
        if q and q not in json.dumps(e).lower():
            continue
        rows.append(e)
    return rows[offset:offset + limit], len(rows)


# ── Request hook ─────────────────────────────────────────────────────────────────────
def _target(response):
    """A human name for what changed: the switch or block name, else the id in the URL."""
    args = request.view_args or {}
    if 'team_id' in args and 'username' in args:   # a membership: who, in which team
        return f"{args['username']} in {args['team_id']}"
    body = response.get_json(silent=True) if response.is_json else None
    sent = request.get_json(silent=True)
    for source in (body, (body or {}).get('user') if isinstance(body, dict) else None, sent):
        if isinstance(source, dict):
            for key in ('name', 'label', 'username', 'title'):
                if isinstance(source.get(key), str) and source[key]:
                    return source[key]
    args = request.view_args or {}
    return next(iter(args.values()), None)


def _changed_fields():
    body = request.get_json(silent=True)
    return list(body) if isinstance(body, dict) else None


def init_audit(app):
    @app.before_request
    def remember_who():
        # Logout clears the session before the response, so note the account now.
        from auth import current_user
        user = current_user()
        g.audit_user = user['username'] if user else None

    @app.after_request
    def log_change(response):
        rule = request.url_rule.rule if request.url_rule else None
        user = g.get('audit_user')
        if rule == '/login' and request.method == 'POST':
            name = (request.form.get('username') or '').strip()[:80]
            ok = response.status_code in (302, 303)
            record('sign-in', 'Signed in' if ok else 'Sign-in failed', user=name or None, ok=ok)
        elif rule == '/logout' and request.method == 'POST' and user:
            record('sign-in', 'Signed out', user=user)
        elif request.endpoint == 'auth.callback':
            provider = (request.view_args or {}).get('provider_id')
            if response.status_code in (302, 303) and session.get('user'):
                record('sign-in', 'Signed in', user=session['user'], target=provider)
            elif response.status_code in (400, 403):
                record('sign-in', 'Sign-in failed', target=provider, ok=False)
        elif response.status_code < 400 and (request.method, rule) in ACTIONS:
            area, action = ACTIONS[(request.method, rule)]
            fields = _changed_fields() if request.method in ('PUT', 'PATCH') else None
            if rule == '/api/settings/backup':
                fields = None
            entry = record(area, action, user=user, target=_target(response), fields=fields)
            for listener in listeners:
                try:
                    listener(entry)
                except Exception as exc:  # noqa: BLE001  # a listener must never break the request
                    print(f'[audit] listener failed: {exc}')
        return response
