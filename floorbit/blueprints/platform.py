"""The platform's tenants, for its admins (issue #466, docs/tenancy.md).

Admins of the default tenant run the platform: they add tenants, rename them, and suspend them.
Every other tenant answers 404 here, so a tenant admin can't see the platform's list.

- ``GET /settings/tenants``: the page (React).
- ``GET /api/platform/tenants``: ``{"tenants": [{id, name, url, status}]}``.
- ``POST /api/platform/tenants`` ``{"id", "name"?, "url"?, "admin"?}``: a new tenant; with ``admin``
  also its first admin account, whose password is in the answer once.
- ``PATCH /api/platform/tenants/<id>`` ``{"name"?, "url"?, "status"?}``: change one; ``status`` is
  ``active`` or ``suspended``.

A suspended tenant's processes answer 503 to everything but the health checks (``suspended_gate``).
"""
import secrets

from flask import Blueprint, abort, current_app, g, jsonify, request

from .. import audit, hosting, i18n, spa, store

bp = Blueprint('platform', __name__)

SUSPENDED = 'This tenant is suspended on this Floorbit platform. Ask the platform admin.'
# Kubernetes keeps asking whether the process lives: a suspended tenant's still does, and a failing
# probe would only restart it over and over.
OPEN_WHILE_SUSPENDED = ('/healthz', '/static/')


def _platform_only():
    if store.current_tenant() != store.DEFAULT_TENANT:
        abort(404)


def _error(exc, status=400):
    return jsonify({'error': i18n.translate(str(exc), i18n.language(request.headers.get('Accept-Language')))}), status


@bp.route('/settings/tenants')
def tenants_page():
    _platform_only()
    return spa.render('Tenants')


@bp.route('/api/platform/tenants', methods=['GET'])
def list_tenants():
    _platform_only()
    return jsonify({'tenants': hosting.tenants(), 'here': store.current_tenant()})


@bp.route('/api/platform/tenants', methods=['POST'])
def add_tenant():
    _platform_only()
    from auth.users import UserError, UserStore  # late: auth imports floorbit while it loads
    body = request.get_json(silent=True) or {}
    admin = str(body.get('admin') or '').strip()
    if admin:
        # Checked before the tenant exists, so a bad name leaves nothing half made.
        try:
            from auth.users import validate_username
            validate_username(admin)
        except UserError as exc:
            return _error(exc)
    try:
        entry = hosting.add(str(body.get('id') or ''), str(body.get('name') or ''), str(body.get('url') or ''))
    except hosting.HostingError as exc:
        return _error(exc)
    password = None
    if admin:
        password = secrets.token_urlsafe(12)
        with store.using(tenant=store.tenant_folder(entry['id']), event=''):
            UserStore(store.tenant_file).add(admin, password, role='admin', created_by=g.get('audit_user'))
    audit.record('platform', 'Added a tenant', user=g.get('audit_user'), target=entry['id'],
                 fields=['admin'] if admin else None)
    return jsonify({'tenant': entry, 'admin': admin or None, 'password': password}), 201


@bp.route('/api/platform/tenants/<tenant_id>', methods=['PATCH'])
def change_tenant(tenant_id):
    _platform_only()
    body = request.get_json(silent=True) or {}
    fields = {k: body[k] for k in ('name', 'url', 'status') if k in body and body[k] is not None}
    try:
        entry = hosting.update(tenant_id, **{k: str(v) for k, v in fields.items()})
    except hosting.HostingError as exc:
        return _error(exc, 404 if hosting.find(tenant_id) is None else 400)
    actions = {'suspended': 'Suspended a tenant', 'active': 'Took a tenant back'}
    action = actions.get(fields.get('status'), 'Changed a tenant')
    audit.record('platform', action, user=g.get('audit_user'), target=tenant_id, fields=list(fields))
    return jsonify({'tenant': entry})


def suspended_gate():
    if not hosting.suspended() or request.path.startswith(OPEN_WHILE_SUSPENDED):
        return None
    lang = i18n.language(request.headers.get('Accept-Language'))
    text = i18n.translate(SUSPENDED, lang)
    if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
        resp = jsonify({'error': text, 'code': 'tenant_suspended'})
    else:
        resp = current_app.make_response((text, 503, {'Content-Type': 'text/plain; charset=utf-8'}))
    resp.status_code = 503
    return resp


def init_app(app):
    # Before sign-in and everything else: a suspended tenant shows nothing, not even its login page.
    app.before_request_funcs.setdefault(None, []).insert(0, suspended_gate)
