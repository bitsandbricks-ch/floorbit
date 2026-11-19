"""The tenant switcher: moving to another tenant of the platform (floorbit/tenant_switch.py).

- ``GET /api/tenant/mine``: ``{"here", "tenants": [{id, name, url, how}]}``, the other tenants the
  signed-in person can switch to. Empty when self-hosted, or while the platform has one tenant.
- ``POST /api/tenant/switch`` ``{"tenant": "<id>"}``: ``{"url"}``, where to send the browser; that
  address signs it in over there, once, within a minute.
- ``GET /switch/arrive?ticket=...``: the other side of it. Open to everyone: the ticket is the key.
- ``GET``/``PUT /api/tenant/platform-access`` ``{"visits": bool}``: whether the platform admins may
  come into this tenant (its admins decide, ``accounts.manage``). ``shown`` says whether it matters
  here: only on a tenant other than the default one.
"""
import time

from flask import Blueprint, current_app, g, jsonify, redirect, request

from auth import current_user, public_endpoint

from .. import audit, hosting, i18n, store, tenant_switch

bp = Blueprint('tenant_switch', __name__)

# memberships() reads every tenant's accounts: once a minute per person is plenty for a sidebar.
REMEMBER = 60.0
_known = {}


def _record(user):
    auth = current_app.extensions.get('auth')
    if not auth or not auth.enabled or not user or user.get('api_token') or user.get('platform'):
        return None
    return auth.users.get(user['username'])


@bp.route('/api/tenant/mine', methods=['GET'])
def mine():
    user = current_user()
    # A tenant added or suspended here shows at once, not a minute later.
    key = (store.current_tenant(), (user or {}).get('username'), (user or {}).get('role'),
           store.generation(hosting.path()))
    hit = _known.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < REMEMBER:
        found = hit[1]
    else:
        found = tenant_switch.reachable(user, _record(user))
        if len(_known) > 1024:
            _known.clear()
        _known[key] = (now, found)
    return jsonify({'here': store.current_tenant(), 'tenants': found})


@bp.route('/api/tenant/switch', methods=['POST'])
def switch():
    user = current_user()
    body = request.get_json(silent=True) or {}
    try:
        url = tenant_switch.issue(user, _record(user), str(body.get('tenant') or ''))
    except tenant_switch.SwitchError as exc:
        lang = i18n.language(request.headers.get('Accept-Language'))
        return jsonify({'error': i18n.translate(str(exc), lang)}), 403
    audit.record('sign-in', 'Switched to another tenant', user=g.get('audit_user'), target=body.get('tenant'))
    return jsonify({'url': url})


@bp.route('/switch/arrive', methods=['GET'])
@public_endpoint
def arrive():
    auth = current_app.extensions.get('auth')
    if not auth or not auth.enabled:
        return redirect('/')
    doc = tenant_switch.take(request.args.get('ticket'))
    who = None
    if doc and doc.get('how') == 'account':
        record = auth.users.get(str(doc.get('username') or ''))
        mine = (record or {}).get('identities') or {}
        # The link that made the ticket must still be there: an unlinked account can't be switched into.
        if record and any(mine.get(p) == s for p, s in (doc.get('identities') or {}).items()):
            auth.sign_in(record, 'switch')
            who = record['username']
    elif doc and doc.get('how') == 'platform':
        record = tenant_switch._platform_record(str(doc.get('username') or ''))
        if record and tenant_switch.visits_allowed():
            visitor = tenant_switch.visitor(record['username'], record.get('display_name'),
                                            record.get('session_version', 1))
            auth.sign_in_visitor(visitor, time.time() + tenant_switch.VISIT_HOURS * 3600)
            who = visitor['username']
    if not who:
        audit.record('sign-in', 'Switch from another tenant refused', ok=False)
        return redirect('/login')
    audit.record('sign-in', 'Came in from another tenant', user=who, target=doc.get('from'))
    return redirect('/')


@bp.route('/api/tenant/platform-access', methods=['GET'])
def platform_access():
    return jsonify({'visits': tenant_switch.visits_allowed(),
                    'shown': store.current_tenant() != store.DEFAULT_TENANT})


@bp.route('/api/tenant/platform-access', methods=['PUT'])
def set_platform_access():
    body = request.get_json(silent=True) or {}
    if store.current_tenant() == store.DEFAULT_TENANT or not isinstance(body.get('visits'), bool):
        lang = i18n.language(request.headers.get('Accept-Language'))
        msg = 'Only another tenant than the default one can turn platform visits off.'
        return jsonify({'error': i18n.translate(msg, lang)}), 400
    tenant_switch.set_visits(body['visits'])
    audit.record('accounts', 'Let platform admins visit' if body['visits'] else 'Turned off platform visits',
                 user=g.get('audit_user'))
    return jsonify({'visits': tenant_switch.visits_allowed(), 'shown': True})
