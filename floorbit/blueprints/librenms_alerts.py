"""LibreNMS alerts through the agent (issue #951, docs/librenms-alerts.md).

- ``GET /api/alerts/librenms/setup``: what to paste into LibreNMS's API transport (URL per agent,
  the token, the body). ``settings.manage``: the token lets someone post alerts.
- ``POST /api/alerts/librenms/token``: a new token; the agents get it with their next config.
- ``DELETE /api/alerts/librenms/<key>``: clears an alert whose recovery never came
  (``incidents.work``, like mutes).
"""
from flask import Blueprint, g, jsonify

from .. import audit, librenms_alerts

bp = Blueprint('librenms_alerts', __name__)


@bp.route('/api/alerts/librenms/setup', methods=['GET'])
def setup():
    body = {**librenms_alerts.setup(), 'token': librenms_alerts.token()}
    audit.record('alerts', 'Looked at the LibreNMS alerts token', g.get('audit_user'))
    return jsonify(body)


@bp.route('/api/alerts/librenms/token', methods=['POST'])
def new_token():
    token = librenms_alerts.new_token()
    audit.record('alerts', 'Made a new LibreNMS alerts token', g.get('audit_user'))
    return jsonify({'token': token})


@bp.route('/api/alerts/librenms/<key>', methods=['DELETE'])
def clear(key):
    found = librenms_alerts.clear(key)
    if not found:
        return jsonify({'error': 'That LibreNMS alert is not open.'}), 404
    audit.record('alerts', 'Cleared a LibreNMS alert', g.get('audit_user'),
                 target=f"{found.get('host')}: {found.get('title')}")
    return jsonify({'ok': True})
