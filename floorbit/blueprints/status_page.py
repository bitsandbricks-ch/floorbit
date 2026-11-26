"""Public network status page (issue #101). The rules live in floorbit/status_page.py.

- ``GET /status``: the page for attendees, no account. Off unless Settings > Attendee pages turns it on.
  ``/hall``, the old attendee view, leads here.
- ``GET /status.json``: the same as JSON, for the event website or a Discord bot.
- ``GET /network-status``: the crew's page (React): what the public page says now, updates, the state
  set by hand.
- ``GET /api/status-page``: what the public page shows, plus who set what.
- ``POST /api/status-page/updates``, ``DELETE /api/status-page/updates/<id>``: the crew's updates.
- ``PUT /api/status-page/override``: ``{"state": "maintenance"}`` sets the state, ``{"state": null}``
  goes back to the automatic one.

Reading the crew's view needs ``incidents.work``, changing it ``incidents.assign`` (auth/roles.py).
"""
from flask import Blueprint, current_app, g, jsonify, redirect, request

from integrations import events

from .. import audit, firewalls, spa, status_page
from ..store import load_data

bp = Blueprint('status_page', __name__)

def _settings():
    return current_app.extensions['floorbit_settings']


def page_on():
    return bool(_settings().get('public.status_page'))


def _monitor():
    return (current_app.extensions.get('floorbit_integrations') or {}).get('monitor')


def _now(show_names=False):
    from .. import sources
    monitor = _monitor()
    statuses = dict(getattr(monitor, 'statuses', None) or {})
    # No poll yet, or the source not answering: say "unknown" rather than "all fine".
    up = bool(monitor and monitor.last_poll) and not sources.offline()
    wall = current_app.extensions.get('floorbit_health')
    # The wall's last poll, not a fresh one: this page is public and must stay cheap.
    checks = wall.snapshot()['checks'] if wall is not None else []
    try:
        routed = firewalls.seat_routes()['seats'] if firewalls.configured() else {}
    except Exception:  # noqa: BLE001 - a firewall plan that can't be read must not take the page down
        routed = {}
    return status_page.current(load_data(), statuses, up, show_names, checks=checks, routed=routed)


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _changed():
    events.publish('status_page.changed', {})


@bp.route('/status')
def status_public():
    """The page itself is React (frontend/src/pages/public/PublicStatus.tsx), reading /status.json;
    404 while it is switched off, so links and monitors see that, and the page says so."""
    html, status = spa.render('Status updates', shell=False)
    return html, status if page_on() else 404


@bp.route('/status.json')
def status_json():
    if not page_on():
        return jsonify({'error': 'The status page is switched off.'}), 404
    body = _now()
    body.pop('auto_state', None)
    body.pop('override', None)   # who set it is the crew's business
    body['updates'] = [{k: u[k] for k in ('at', 'text', 'state', 'area')} for u in body['updates']]
    return jsonify(body)


@bp.route('/hall')
def old_hall_view():
    # The attendee view with a dot per seat went (it showed when a player was away); links to it
    # land on the status page, which says what attendees need: is the network fine, and where not.
    return redirect('/status', 301)


for _view in (status_public, status_json, old_hall_view):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account


@bp.route('/network-status')
def crew_page():
    return spa.render('Status updates')


@bp.route('/api/status-page', methods=['GET'])
def crew_view():
    body = _now()
    body['public'] = page_on()
    # The crew sees which switches; the public page never does.
    crew = _now(show_names=True)
    body['crew_areas'] = crew['areas']
    body['crew_recovered'] = crew['recovered']   # issue #396: what the public page lists as back up
    return jsonify(body)


@bp.route('/api/status-page/updates', methods=['POST'])
def add_update():
    try:
        update = publish_update(request.get_json(silent=True) or {}, _who(), g.get('audit_user'))
    except status_page.StatusError as exc:
        return jsonify({'error': str(exc)}), exc.status
    return jsonify(update), 201


def publish_update(body, by, audit_user, label='Posted status update'):
    """Post a crew update and tell everyone who listens. Also used by the Discord bot's /statusupdate."""
    update = status_page.post_update(body, by)
    audit.record('status page', label, audit_user, update['text'][:120])
    _changed()
    return update


@bp.route('/api/status-page/updates/<update_id>', methods=['DELETE'])
def remove_update(update_id):
    try:
        status_page.delete_update(update_id)
    except status_page.StatusError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('status page', 'Removed status update', g.get('audit_user'), update_id)
    _changed()
    return jsonify({'ok': True})


@bp.route('/api/status-page/override', methods=['PUT'])
def override():
    try:
        result = status_page.set_override(request.get_json(silent=True) or {}, _who())
    except status_page.StatusError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('status page', f"Set status to {result['state']}" if result else 'Set status back to automatic',
                 g.get('audit_user'), (result or {}).get('note') or None)
    _changed()
    return jsonify({'override': result})
