"""The public attendee view (issue #19). See docs/kiosk.md.

- ``GET /hall``: the hall plan with every seat shown as online or offline, for attendees' phones and
  the event website. No account.
- ``GET /api/public/hall``: the hall's drawing for the page, with which seats are online.
- ``GET /api/public/seats``: the same as JSON, which the page reloads every minute. ``?hall=<id>``
  for one hall; ``/hall?hall=<id>`` shows that hall, with tabs for the others.

Seat numbers and online or not, nothing else: no nicks, IPs, MACs, switches or ports. Off unless
"Attendee view" is switched on in Settings, because it shows when a seat's player is away.
"""
import time

from flask import Blueprint, current_app, jsonify, request

from .. import halls, spa
from ..seat_names import block_rows
from ..store import load_data
from .screen import finder_on, plan

bp = Blueprint('attendee', __name__)


def view_on():
    return bool(current_app.extensions['floorbit_settings'].get('public.attendee_view'))


def _online(now=None):
    """The online seats from the latest port read, or None when there is no recent read."""
    from ..attention import AttentionWatch
    seats = current_app.extensions['floorbit_stats'].seats()
    last = seats.get('last_poll')
    now = time.time() if now is None else now
    # Three missed reads and the dots would lie; better to say we don't know.
    if not last or now - last > 3 * AttentionWatch.interval():
        return None, last
    return set(seats.get('seats') or {}), last


@bp.route('/hall')
def hall_page():
    """The page is React (frontend/src/pages/public/PublicHall.tsx), reading /api/public/hall and
    then /api/public/seats every minute; 404 while it is switched off."""
    html, status = spa.render('Hall overview')
    return html, status if view_on() else 404


@bp.route('/api/public/hall')
def public_hall():
    """One hall's drawing for the page (``?hall=<id>``, else the first), the other halls to switch to,
    and which seats are online: the same seat numbers and true/false as /api/public/seats."""
    if not view_on():
        return jsonify({'error': 'The attendee view is switched off.'}), 404
    data = load_data()
    all_halls = halls.halls(data)
    hall = halls.find(data, request.args.get('hall') or '') or all_halls[0]
    online, last = _online()
    drawing, _ = plan(data, online=online if online is not None else set(), hall_id=hall['id'], public=True)
    settings = current_app.extensions['floorbit_settings']
    tabs = [{'id': h['id'], 'name': h['name']} for h in all_halls] if len(all_halls) > 1 else []
    body = {'hall': hall['id'], 'halls': tabs,
            'drawing': drawing, 'updated': last, 'finder': finder_on(), 'agenda': bool(settings.get('public.schedule'))}
    cells = [c for b in (drawing or {}).get('shapes', []) for c in b['cells']]
    body['total'] = len(cells)
    body['online'] = None if online is None else sum(1 for c in cells if c['on'])
    if online is None:
        for c in cells:
            c['on'] = None
    return jsonify(body)


@bp.route('/api/public/seats')
def public_seats():
    if not view_on():
        return jsonify({'error': 'The attendee view is switched off.'}), 404
    data = load_data()
    wanted = request.args.get('hall')
    ids = {h['id'] for h in halls.halls(data)}
    seats = [seat for b in data.get('seat_blocks') or [] if not wanted or halls.hall_of(b, data, ids) == wanted
             for row in block_rows(b) for seat in row]
    online, last = _online()
    if online is None:
        return jsonify({'seats': dict.fromkeys(seats), 'online': None, 'total': len(seats), 'updated': last})
    return jsonify({'seats': {s: s in online for s in seats}, 'online': sum(1 for s in seats if s in online),
                    'total': len(seats), 'updated': last})


for _view in (hall_page, public_hall, public_seats):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account
