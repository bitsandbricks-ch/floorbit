"""Event changelog (issue #100). The rules live in floorbit/timeline.py.

- ``GET /timeline``: the page (React).
- ``GET /api/timeline?kinds=change,outage&q=&hours=&before=``: entries, newest first, with counts
  per kind. ``hours`` limits it to the last hours, ``before`` (a unix time) pages back.
- ``GET /api/timeline.csv`` with the same filters, and ``?format=json`` on ``/api/timeline`` for
  everything at once.

It holds the audit log, so it needs ``audit.read``.
"""
import time

from flask import Blueprint, Response, current_app, jsonify, request

from .. import spa, timeline

bp = Blueprint('timeline', __name__)
PAGE = 300


def _query():
    kinds = {k for k in (request.args.get('kinds') or '').split(',') if k in timeline.KINDS} or None
    since = until = None
    try:
        hours = float(request.args.get('hours') or 0)
        if hours > 0:
            since = time.time() - hours * 3600
        if request.args.get('before'):
            until = float(request.args['before'])
    except ValueError:
        pass
    events = current_app.extensions['floorbit_stats'].event().get('switch_events') or []
    return dict(switch_events=events, kinds=kinds, q=request.args.get('q') or '', since=since, until=until)


@bp.route('/timeline')
def timeline_page():
    return spa.render('Event changelog')


@bp.route('/api/timeline', methods=['GET'])
def entries():
    whole = request.args.get('format') == 'json'
    rows, total, counts = timeline.build(**_query(), limit=timeline.MAX_ROWS if whole else PAGE)
    body = {'entries': rows, 'total': total, 'counts': counts, 'kinds': list(timeline.KINDS),
            'more': total > len(rows)}
    if whole:
        return Response(jsonify(body).get_data(), mimetype='application/json',
                        headers={'Content-Disposition': 'attachment; filename="event-changelog.json"'})
    return jsonify(body)


@bp.route('/api/timeline.csv', methods=['GET'])
def csv_export():
    rows, _total, _counts = timeline.build(**_query())
    headers = {'Content-Disposition': 'attachment; filename="event-changelog.csv"', 'Cache-Control': 'no-store'}
    return Response(timeline.csv_text(rows), mimetype='text/csv', headers=headers)
