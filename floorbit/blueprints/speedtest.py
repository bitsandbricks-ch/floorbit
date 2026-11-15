"""Speedtest at the seat (issue #99). The rules live in floorbit/speedtest.py.

The seat's help page (``/help/<seat>?k=<signature>``) runs the test against these, with the same
signed link and no account:

- ``GET /help/<seat>/speed/ping``: an empty answer, for latency.
- ``GET /help/<seat>/speed/down?bytes=``: random bytes to download.
- ``POST /help/<seat>/speed/up``: bytes to upload, read and dropped.
- ``POST /help/<seat>/speed/result``: ``{down_mbps, up_mbps, ping_ms, jitter_ms}``, kept for the seat.

``GET /api/speedtests?seat=``: the latest results per seat, for the crew (``incidents.work``).
"""
from flask import Blueprint, Response, abort, jsonify, request

from integrations import events

from .. import audit, incidents, speedtest
from ..store import load_data

bp = Blueprint('speedtest', __name__)


def _seat(seat):
    """The seat, when the link is signed for it and it is on the floor plan; else 404."""
    seat = seat.strip().upper()
    if not (incidents.signed(seat, request.args.get('k')) and seat in incidents.seat_numbers(load_data())):
        abort(404)
    return seat


def _no_store(resp):
    resp.headers['Cache-Control'] = 'no-store, no-transform'
    return resp


def _error(exc):
    return _no_store(jsonify({'error': str(exc)})), exc.status


def _public(view):
    view._auth_public = True   # what auth.public_endpoint sets: the attendee has no account
    return view


@bp.route('/help/<seat>/speed/ping', methods=['GET'])
@_public
def ping(seat):
    _seat(seat)
    return _no_store(Response(b'', mimetype='application/octet-stream'))


@bp.route('/help/<seat>/speed/down', methods=['GET'])
@_public
def down(seat):
    _seat(seat)
    try:
        size = max(1, min(int(request.args.get('bytes') or 0), speedtest.MAX_DOWN))
    except ValueError:
        return _error(speedtest.SpeedtestError('bytes is a number.'))
    try:
        speedtest.take(request.remote_addr or '?', size)
    except speedtest.SpeedtestError as exc:
        return _error(exc)
    resp = Response(speedtest.download(size), mimetype='application/octet-stream', direct_passthrough=True)
    resp.headers['Content-Length'] = str(size)
    resp.headers['X-Accel-Buffering'] = 'no'   # nginx in front: send it as it comes
    return _no_store(resp)


@bp.route('/help/<seat>/speed/up', methods=['POST'])
@_public
def up(seat):
    _seat(seat)
    size = min(request.content_length or 0, speedtest.MAX_UP)
    if size <= 0:
        return _error(speedtest.SpeedtestError('Send the bytes to upload.', 411))
    try:
        speedtest.take(request.remote_addr or '?', size)
    except speedtest.SpeedtestError as exc:
        return _error(exc)
    got = speedtest.swallow(request.stream, size)
    return _no_store(jsonify({'bytes': got}))


@bp.route('/help/<seat>/speed/result', methods=['POST'])
@_public
def result(seat):
    seat = _seat(seat)
    if not speedtest.allow_result(request.remote_addr or '?'):
        return _error(speedtest.SpeedtestError('Too many tests from here. Wait a few minutes.', 429))
    try:
        found = speedtest.clean(request.get_json(silent=True) or {})
    except speedtest.SpeedtestError as exc:
        return _error(exc)
    speedtest.save(seat, found)
    audit.record('incidents', 'Ran a speed test at the seat', target=seat)
    events.publish('incident.changed', {'seat': seat, 'action': 'speedtest'})
    return _no_store(jsonify(found))


@bp.route('/api/speedtests', methods=['GET'])
def recent():
    data = load_data()
    seat = (request.args.get('seat') or '').strip().upper()
    kept = data.get(speedtest.KEY) or {}
    if seat:
        return jsonify({'seats': {seat: kept.get(seat) or []}})
    return jsonify({'seats': kept})
