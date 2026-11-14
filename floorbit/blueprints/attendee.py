"""The public attendee view (issue #19). See docs/kiosk.md.

- ``GET /hall``: the hall plan with every seat shown as online or offline, for attendees' phones and
  the event website. No account.
- ``GET /api/public/seats``: the same as JSON, which the page reloads every minute.

Seat numbers and online or not, nothing else: no nicks, IPs, MACs, switches or ports. Off unless
"Attendee view" is switched on in Settings, because it shows when a seat's player is away.
"""
import time

from flask import Blueprint, current_app, jsonify, render_template, request

from ..store import load_data
from .screen import finder_on, plan

bp = Blueprint('attendee', __name__)

TEXTS = {
    'en': {'title': 'Hall overview', 'intro': 'Which seats are online right now.', 'online': 'online',
           'offline': 'offline', 'count': '{online} of {total} seats online', 'updated': 'Updated {time}',
           'unknown': 'The network status is not available right now.', 'off': 'This page is switched off.',
           'empty': 'There is no hall plan yet.', 'map': 'Hall plan, online seats marked',
           'find': 'Find your seat'},
    'de': {'title': 'Hallenübersicht', 'intro': 'Welche Plätze gerade online sind.', 'online': 'online',
           'offline': 'offline', 'count': '{online} von {total} Plätzen online', 'updated': 'Stand {time}',
           'unknown': 'Der Netzwerkstatus ist gerade nicht verfügbar.', 'off': 'Diese Seite ist ausgeschaltet.',
           'empty': 'Es gibt noch keinen Hallenplan.', 'map': 'Hallenplan, Plätze online markiert',
           'find': 'Finde deinen Platz'},
}


def view_on():
    return bool(current_app.extensions['floorbit_settings'].get('public.attendee_view'))


def _texts():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    return lang, TEXTS[lang]


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
    lang, text = _texts()
    if not view_on():
        return render_template('hall.html', lang=lang, t=text, state='off'), 404
    data = load_data()
    online, last = _online()
    drawing, _ = plan(data, online=online if online is not None else set())
    if not drawing:
        return render_template('hall.html', lang=lang, t=text, state='empty')
    total = sum(len(b['cells']) for b in drawing['shapes'])
    count = sum(1 for b in drawing['shapes'] for c in b['cells'] if c['on'])
    return render_template('hall.html', lang=lang, t=text, state='ok' if online is not None else 'unknown',
                           drawing=drawing, total=total, count=count, last=last, finder=finder_on())


@bp.route('/api/public/seats')
def public_seats():
    if not view_on():
        return jsonify({'error': 'The attendee view is switched off.'}), 404
    drawing, _ = plan(load_data())
    seats = [c['seat'] for b in (drawing or {}).get('shapes', []) for c in b['cells']]
    online, last = _online()
    if online is None:
        return jsonify({'seats': dict.fromkeys(seats), 'online': None, 'total': len(seats), 'updated': last})
    return jsonify({'seats': {s: s in online for s in seats}, 'online': sum(1 for s in seats if s in online),
                    'total': len(seats), 'updated': last})


for _view in (hall_page, public_seats):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account
