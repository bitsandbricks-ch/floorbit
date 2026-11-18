"""The club switcher: moving to another tenant of the platform (floorbit/tenant_switch.py).

- ``GET /api/tenant/mine``: ``{"here", "tenants": [{id, name, url, how}]}``, the other tenants the
  signed-in person can switch to. Empty when self-hosted, or while the platform has one tenant.
- ``POST /api/tenant/switch`` ``{"tenant": "<id>"}``: ``{"url"}``, where to send the browser; that
  address signs it in over there, once, within a minute.
- ``GET /switch/arrive?ticket=...``: the other side of it. Open to everyone: the ticket is the key.
"""
import time

from flask import Blueprint, current_app, g, jsonify, redirect, request

from auth import current_user, public_endpoint

from .. import audit, i18n, store, tenant_switch

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
    key = (store.current_tenant(), (user or {}).get('username'), (user or {}).get('role'))
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
    audit.record('sign-in', 'Switched to another club', user=g.get('audit_user'), target=body.get('tenant'))
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
        if record:
            visitor = tenant_switch.visitor(record['username'], record.get('display_name'),
                                            record.get('session_version', 1))
            auth.sign_in_visitor(visitor, time.time() + tenant_switch.VISIT_HOURS * 3600)
            who = visitor['username']
    if not who:
        audit.record('sign-in', 'Switch from another club refused', ok=False)
        return redirect('/login')
    audit.record('sign-in', 'Came in from another club', user=who, target=doc.get('from'))
    return redirect('/')
