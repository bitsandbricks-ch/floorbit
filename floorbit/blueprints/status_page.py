"""Public network status page (issue #101). The rules live in floorbit/status_page.py.

- ``GET /status``: the page for attendees, no account. Off unless Settings > Attendee pages turns it on.
- ``GET /status.json``: the same as JSON, for the event website or a Discord bot.
- ``GET /network-status``: the crew's page (React): what the public page says now, updates, the state
  set by hand.
- ``GET /api/status-page``: what the public page shows, plus who set what.
- ``POST /api/status-page/updates``, ``DELETE /api/status-page/updates/<id>``: the crew's updates.
- ``PUT /api/status-page/override``: ``{"state": "maintenance"}`` sets the state, ``{"state": null}``
  goes back to the automatic one.

Reading the crew's view needs ``incidents.work``, changing it ``incidents.assign`` (auth/roles.py).
"""
import time

from flask import Blueprint, current_app, g, jsonify, render_template, request
from markupsafe import Markup, escape

from integrations import events

from .. import audit, spa, status_page
from ..store import load_data

bp = Blueprint('status_page', __name__)

TEXTS = {
    'en': {'title': 'Network status', 'off': 'This page is switched off.',
           'state': {'operational': 'All systems running', 'degraded': 'Part of the network is down',
                     'outage': 'Network outage', 'maintenance': 'Maintenance',
                     'unknown': 'Status not available right now'},
           'detail': {'operational': 'The network is working normally.',
                      'degraded': 'Some seats have no network. The crew is on it.',
                      'outage': 'Large parts of the network are down. The crew is on it.',
                      'maintenance': 'The crew is working on the network.',
                      'unknown': 'Floorbit cannot reach its monitoring right now, so it does not know.'},
           'since': 'Since {time}', 'areas': 'Affected areas', 'rows': 'rows {rows}', 'seats': '{n} seats',
           'switches': 'Switches: {names}', 'updates': 'Updates from the crew', 'none': 'No updates yet.',
           'updated': 'Updated {time}. This page reloads every minute.', 'block': 'Seat block {name}',
           'unnamed': 'A seat block', 'hall_wide': 'Hall {name}', 'somewhere': 'Somewhere in the hall'},
    'de': {'title': 'Netzwerkstatus', 'off': 'Diese Seite ist ausgeschaltet.',
           'state': {'operational': 'Alles läuft', 'degraded': 'Ein Teil des Netzwerks ist ausgefallen',
                     'outage': 'Netzwerkausfall', 'maintenance': 'Wartung',
                     'unknown': 'Status gerade nicht verfügbar'},
           'detail': {'operational': 'Das Netzwerk läuft normal.',
                      'degraded': 'Einige Plätze haben kein Netzwerk. Die Crew ist dran.',
                      'outage': 'Grosse Teile des Netzwerks sind ausgefallen. Die Crew ist dran.',
                      'maintenance': 'Die Crew arbeitet am Netzwerk.',
                      'unknown': 'Floorbit erreicht sein Monitoring gerade nicht und weiss es darum nicht.'},
           'since': 'Seit {time}', 'areas': 'Betroffene Bereiche', 'rows': 'Reihen {rows}',
           'seats': '{n} Plätze', 'switches': 'Switches: {names}', 'updates': 'Updates der Crew',
           'none': 'Noch keine Updates.', 'updated': 'Stand {time}. Die Seite lädt jede Minute neu.',
           'block': 'Platzblock {name}', 'unnamed': 'Ein Platzblock', 'hall_wide': 'Halle {name}',
           'somewhere': 'Irgendwo in der Halle'},
}


def _settings():
    return current_app.extensions['floorbit_settings']


def page_on():
    return bool(_settings().get('public.status_page'))


def _monitor():
    return (current_app.extensions.get('lal_integrations') or {}).get('monitor')


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


def _stamp(text, at):
    """``text`` with ``{time}`` as a <time> the page's script shows in the reader's own time zone."""
    clock = time.strftime('%H:%M', time.localtime(at))
    tag = Markup('<time data-at="{}">{}</time>').format(int(at), clock)
    return Markup(str(escape(text)).replace('{time}', str(tag)))


def _changed():
    events.publish('status_page.changed', {})


@bp.route('/status')
def status_public():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    text = TEXTS[lang]
    if not page_on():
        return render_template('status.html', lang=lang, t=text, off=True), 404
    return render_template('status.html', lang=lang, t=text, off=False, s=_now(), stamp=_stamp)


@bp.route('/status.json')
def status_json():
    if not page_on():
        return jsonify({'error': 'The status page is switched off.'}), 404
    body = _now()
    body.pop('auto_state', None)
    body.pop('override', None)   # who set it is the crew's business
    body['updates'] = [{k: u[k] for k in ('at', 'text', 'state', 'area')} for u in body['updates']]
    return jsonify(body)


for _view in (status_public, status_json):
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
    body['crew_areas'] = _now(show_names=True)['areas']
    return jsonify(body)


@bp.route('/api/status-page/updates', methods=['POST'])
def add_update():
    try:
        update = status_page.post_update(request.get_json(silent=True) or {}, _who())
    except status_page.StatusError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('status page', 'Posted status update', g.get('audit_user'), update['text'][:120])
    _changed()
    return jsonify(update), 201


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
