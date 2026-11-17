"""Public network status page (issue #101). The rules live in floorbit/status_page.py.

- ``GET /status``: the page for attendees, no account. Off unless Settings > Attendee pages turns it on.
- ``GET /status.json``: the same as JSON, for the event website or a Discord bot.
- ``GET /status.atom``: the crew's updates as an Atom feed, for feed readers and the event website.
- ``GET /network-status``: the crew's page (React): what the public page says now, updates, the state
  set by hand.
- ``GET /api/status-page``: what the public page shows, plus who set what.
- ``POST /api/status-page/updates``, ``DELETE /api/status-page/updates/<id>``: the crew's updates.
- ``POST /api/status-page/maintenance``, ``DELETE /api/status-page/maintenance/<id>``: planned
  maintenance, announced ahead (issue #422).
- ``PUT /api/status-page/override``: ``{"state": "maintenance"}`` sets the state, ``{"state": null}``
  goes back to the automatic one.

Reading the crew's view needs ``incidents.work``, changing it ``incidents.assign`` (auth/roles.py).
"""
import time

from flask import Blueprint, Response, current_app, g, jsonify, request

from integrations import events

from .. import audit, spa, status_page
from ..store import load_data

bp = Blueprint('status_page', __name__)

# What the Atom feed needs; the page's own texts are in frontend/src/i18n/*/publicStatus.json.
TEXTS = {
    'en': {'title': 'Network status',
           'state': {'operational': 'All systems running', 'degraded': 'Part of the network is down',
                     'outage': 'Network outage', 'maintenance': 'Maintenance',
                     'unknown': 'Status not available right now'}},
    'de': {'title': 'Netzwerkstatus',
           'state': {'operational': 'Alles läuft', 'degraded': 'Ein Teil des Netzwerks ist ausgefallen',
                     'outage': 'Netzwerkausfall', 'maintenance': 'Wartung',
                     'unknown': 'Status gerade nicht verfügbar'}},
}


def _settings():
    return current_app.extensions['floorbit_settings']


def page_on():
    return bool(_settings().get('public.status_page'))


def _monitor():
    return (current_app.extensions.get('floorbit_integrations') or {}).get('monitor')


def _now(show_names=None):
    from .. import sources
    monitor = _monitor()
    statuses = dict(getattr(monitor, 'statuses', None) or {})
    # No poll yet, or the source not answering: say "unknown" rather than "all fine".
    up = bool(monitor and monitor.last_poll) and not sources.offline()
    if show_names is None:
        show_names = bool(_settings().get('public.status_switch_names'))
    return status_page.current(load_data(), statuses, up, show_names)


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')



def _base_url():
    return (current_app.extensions['auth'].public_url() or '').rstrip('/') or request.host_url.rstrip('/')


def _changed():
    events.publish('status_page.changed', {})


@bp.route('/status')
def status_public():
    """The page itself is React (frontend/src/pages/public/PublicStatus.tsx), reading /status.json;
    404 while it is switched off, so links and monitors see that, and the page says so."""
    html, status = spa.render('Network status')
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


@bp.route('/status.atom')
def status_atom():
    if not page_on():
        return jsonify({'error': 'The status page is switched off.'}), 404
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    text = TEXTS[lang]
    name = _settings().get('theme.name') or ''
    base = _base_url()
    feed = status_page.atom_feed(_now()['updates'], base, f"{text['title']}{' · ' + name if name else ''}",
                                 text['state'])
    return Response(feed, mimetype='application/atom+xml', headers={'Cache-Control': 'max-age=60'})


for _view in (status_public, status_json, status_atom):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account


@bp.route('/network-status')
def crew_page():
    return spa.render('Network status')


@bp.route('/api/status-page', methods=['GET'])
def crew_view():
    body = _now()
    body['public'] = page_on()
    body['switch_names'] = bool(_settings().get('public.status_switch_names'))
    # The crew always sees which switches; the public page only when an admin allows it.
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
    # For the attendees' Discord channel (integrations/discord.py): never who posted.
    events.publish('status_page.update', {
        'update': {k: update[k] for k in ('at', 'text', 'state', 'area')}, 'public': page_on(),
        'page_url': _base_url() + '/status'})
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


@bp.route('/api/status-page/maintenance', methods=['POST'])
def plan_maintenance():
    try:
        item = status_page.plan_maintenance(request.get_json(silent=True) or {}, _who())
    except status_page.StatusError as exc:
        return jsonify({'error': str(exc)}), exc.status
    when = time.strftime('%d.%m. %H:%M', time.localtime(item['start']))
    audit.record('status page', 'Planned maintenance', g.get('audit_user'), f"{when}: {item['text'][:100]}")
    _changed()
    return jsonify(item), 201


@bp.route('/api/status-page/maintenance/<item_id>', methods=['DELETE'])
def cancel_maintenance(item_id):
    try:
        status_page.cancel_maintenance(item_id)
    except status_page.StatusError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('status page', 'Cancelled planned maintenance', g.get('audit_user'), item_id)
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
