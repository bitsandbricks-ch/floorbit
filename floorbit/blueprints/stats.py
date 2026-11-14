"""The stats dashboard (issue #24). See docs/stats.md.

- ``GET /stats``: the page; ``/stats?screen=1`` is the big-screen version for kiosk and ops screens.
- ``GET /api/stats``: bandwidth now, the hour, the day and the event's peak, uplinks, online seats,
  port counts and top talkers. Nicks are added to the top talkers only for ``seats.view`` and never
  with ``?screen=1``, which a kiosk shows to everyone.
- ``POST /api/stats/peak/reset``: start the event's peak again (``settings.manage``), e.g. after
  load tests before doors open.
"""
from flask import Blueprint, current_app, jsonify, request

from integrations import events, seat_sources

from .. import sources, spa

bp = Blueprint('stats', __name__)


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


def _stats():
    return current_app.extensions['floorbit_stats']


@bp.route('/stats')
def stats_page():
    return spa.render('Stats')


@bp.route('/api/stats', methods=['GET'])
def get_stats():
    from ..attention import AttentionWatch
    out = _stats().snapshot()
    out['monitoring'] = sources.monitoring().enabled()
    out['interval'] = AttentionWatch.interval()
    if request.args.get('screen') != '1' and _can('seats.view') and out['top']:
        seats = seat_sources.load()
        for t in out['top']:
            if t['seat']:
                t['nick'] = (seats.get(t['seat']) or {}).get('username') or None
    return jsonify(out)


@bp.route('/api/stats/peak/reset', methods=['POST'])
def reset_peak():
    _stats().reset_peak()
    events.publish('stats.changed', {})
    return jsonify(_stats().snapshot())
