"""The stats dashboard (issue #24). See docs/stats.md.

- ``GET /stats``: the page; ``/stats?screen=1`` is the big-screen version for kiosk and ops screens.
- ``GET /api/stats``: bandwidth now, the hour, the day and the event's peak, uplinks, online seats,
  port counts and top talkers. Nicks are added to the top talkers only for ``seats.view`` and never
  with ``?screen=1``, which a kiosk shows to everyone.
- ``GET /api/stats/compare``: today against yesterday, and this event against the last archived one, each
  cut to the same length (floorbit/compare.py).
- ``GET /api/forecast``: the bandwidth forecast for the next hours (floorbit/forecast.py).
- ``GET /api/stats/seats``: traffic per online seat right now (seat numbers only), for the kiosk.
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


@bp.route('/api/stats/compare', methods=['GET'])
def get_compare():
    from .. import compare, features, incidents, report
    from ..store import load_data
    from .replay import _checkins
    stats_event = _stats().event()
    out = {'day': compare.day(stats_event), 'event': None}
    if features.on('report') and features.on('past_events'):
        built = report.build(stats_event, _checkins(), len(incidents.seat_numbers(load_data())))
        out['event'] = compare.event(built)
    return jsonify(out)


@bp.route('/api/forecast', methods=['GET'])
def get_forecast():
    return jsonify(current_app.extensions['floorbit_forecast'].current())


@bp.route('/api/stats/seats', methods=['GET'])
def seat_traffic():
    """Traffic per online seat, for the kiosk's heat view (``/kiosk?view=heat``)."""
    return jsonify(_stats().seats())


@bp.route('/api/stats/peak/reset', methods=['POST'])
def reset_peak():
    _stats().reset_peak()
    events.publish('stats.changed', {})
    return jsonify(_stats().snapshot())
