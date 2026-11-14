"""Shift handover (issue #33). Rules in floorbit/handover.py.

- ``GET /handover``: the page (React).
- ``GET /api/handover``: what happened since the last handover, and the last handovers.
- ``POST /api/handover``: hand over, with a note for the next shift; ``discord: true`` also posts the
  summary to the crew channel (or the alert webhook).

Both need ``incidents.work``: the summary is the crew's, with names from the audit log.
"""
from flask import Blueprint, current_app, jsonify, request

from integrations import config, events

from .. import handover, problems, spa

bp = Blueprint('handover', __name__)


def _user():
    from auth import current_user  # late: auth imports floorbit while it loads
    return current_user() or {}


def _summary():
    stats = current_app.extensions['floorbit_stats'].event()
    return handover.summary(stats['switch_events'], problems.current(False)['counts'])


@bp.route('/handover')
def handover_page():
    return spa.render('Shift handover')


@bp.route('/api/handover', methods=['GET'])
def get_summary():
    out = _summary()
    out['history'] = handover.history()[:10]
    out['discord'] = bool(current_app.extensions.get('floorbit_discord')
                          and current_app.extensions['floorbit_discord'].enabled())
    return jsonify(out)


@bp.route('/api/handover', methods=['POST'])
def hand_over():
    body = request.get_json(silent=True) or {}
    built = _summary()
    user = _user()
    record = handover.hand_over(user.get('display_name') or user.get('username'), body.get('note'),
                                built['counts'], built['since'])
    posted = None
    notifier = current_app.extensions.get('floorbit_discord')
    if body.get('discord') and notifier is not None and notifier.enabled():
        notifier.post(handover.discord_message(record, built, config.get('PUBLIC_URL', '') or '',
                                               config.get('DISCORD_USERNAME', 'Floorbit')))
        posted = True
    events.publish('handover.changed', {'id': record['id']})
    return jsonify({**record, 'posted': posted}), 201
