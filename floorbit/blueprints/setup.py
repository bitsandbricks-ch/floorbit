"""First-run setup (issue #13, floorbit/setup.py).

- ``GET /setup``: the wizard. Open without an account, because a new install has none yet.
- ``GET /api/setup``: whether an account or setup is still needed; the steps for admins.
- ``POST /api/setup/account``: the first admin, with the setup code from the log. Only while
  there are no accounts.
- ``POST /api/setup/steps/<step>``: mark a step done or skipped (``settings.manage``).
- ``POST /api/setup/finish``: setup is over; the floor plan stops sending admins here.

Connecting NetBox and LibreNMS, the import and the theme use the settings, test and sync APIs.
"""
from flask import Blueprint, current_app, jsonify, redirect, request

from .. import inventory, setup, spa
from ..store import load_data

bp = Blueprint('setup', __name__)


def current_user():
    from auth import current_user as signed_in  # late: auth imports floorbit while it loads
    return signed_in()


def public_endpoint(view):
    view._auth_public = True   # what auth.public_endpoint sets (auth can't be imported here yet)
    return view


def _auth():
    return current_app.extensions.get('auth')


def _no_accounts():
    auth = _auth()
    return bool(auth and auth.enabled and auth.users.count() == 0)


def _code():
    return current_app.extensions['floorbit_setup_code']


def _may_set_up(user):
    auth = _auth()
    from auth import roles
    return not (auth and auth.enabled) or bool(user and roles.can(user, 'settings.manage'))


@bp.route('/setup')
@public_endpoint
def setup_page():
    user = current_user()
    if not _no_accounts() and not _may_set_up(user):
        return redirect('/login?next=/setup' if not user else '/')
    return spa.render('Set up Floorbit')


@bp.route('/api/setup', methods=['GET'])
@public_endpoint
def overview():
    if _no_accounts():
        return jsonify({'needs_account': True, 'done': False})
    user = current_user()
    st = setup.state()
    if not _may_set_up(user):
        return jsonify({'needs_account': False, 'done': st['done']})
    store = current_app.extensions['floorbit_settings']
    data = load_data()
    devices = inventory.devices(data)
    return jsonify({
        'needs_account': False, 'done': st['done'], 'steps': st['steps'], 'can_set_up': True,
        'netbox': bool(store.get('netbox.url') and store.get('netbox.token')),
        'librenms': bool(store.get('librenms.url') and store.get('librenms.token')),
        'switches': {'total': len(devices), 'placed': sum(d.get('x') is not None for d in devices)},
        'theme': store.get('theme.preset'),
    })


@bp.route('/api/setup/account', methods=['POST'])
@public_endpoint
def first_account():
    if not _no_accounts():
        return jsonify({'error': 'There is an account already. Sign in instead.'}), 409
    body = request.get_json(silent=True) or {}
    if not _code().check(body.get('code')):
        return jsonify({'error': "That setup code isn't right. It is in Floorbit's log "
                                 '(docker compose logs floorbit).'}), 403
    auth = _auth()
    try:
        user = auth.users.add((body.get('username') or '').strip(), body.get('password') or '',
                              display_name=(body.get('display_name') or '').strip() or None, role='admin')
    except ValueError as exc:
        _code().issue()   # the right code was used up; the log shows the next one
        return jsonify({'error': str(exc), 'new_code': True}), 400
    auth.sign_in(user, 'password')
    return jsonify({'username': user['username']}), 201


@bp.route('/api/setup/steps/<step>', methods=['POST'])
def mark_step(step):
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(setup.set_step(step, body.get('state')))
    except setup.SetupError as exc:
        return jsonify({'error': str(exc)}), 400


@bp.route('/api/setup/finish', methods=['POST'])
def finish():
    user = current_user()
    return jsonify(setup.finish(user['username'] if user else None))


def init_setup(app):
    app.extensions['floorbit_setup_code'] = code = setup.SetupCode()
    setup.mark_existing()
    auth = app.extensions.get('auth')
    if auth and auth.enabled and auth.users.count() == 0:
        code.issue()

    @app.before_request
    def send_admins_to_setup():
        # Only the floor plan page sends people on, and only someone who can do the setup.
        if request.method != 'GET' or request.path != '/':
            return None
        if _no_accounts():
            return redirect('/setup')
        user = current_user()
        if user and _may_set_up(user) and setup.needed():
            return redirect('/setup')
        return None
