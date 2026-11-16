"""The HTML pages of the editor and the kiosk view, and the list of pages for "Go to"."""
from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, redirect, render_template, request

from .. import nav, page_index, seat_view, spa

bp = Blueprint('pages', __name__)


@bp.app_context_processor
def nav_context():
    # The sidebar on every crew page (templates/_nav.html).
    return nav.context()


@bp.route('/')
def index():
    """The floor plan is the React workspace now (``/plan``); its Edit mode does what this page's
    editor did. Old links (``/?hall=``, ``/?seat=``, ``/?switch=`` from Problems and incidents) open
    there, in Edit mode for an account that may edit, since they meant "show it in the editor"."""
    from auth import current_user, roles
    args = request.args.to_dict()
    user = current_user()
    if args and user and roles.can(user, 'floorplan.edit'):
        args.setdefault('mode', 'edit')
    return redirect('/plan' + (f'?{urlencode(args)}' if args else ''))


@bp.route('/editor/classic')
def classic_editor():
    """The older editor, kept for a while as a fallback; nothing links to it but Edit mode's panel."""
    return render_template('index.html')


@bp.route('/kiosk')
def kiosk():
    """Read-only floor plan for a big screen (see docs/kiosk.md)."""
    return render_template('kiosk.html')


@bp.route('/checkin')
def checkin_page():
    """Seat check-in for attendees (frontend/src/pages/Checkin.tsx), which says itself when check-in
    isn't open; 404 then, as before."""
    from integrations import config
    html, status = spa.render('Seat check-in')
    return html, status if config.get_bool('CHECKIN_ENABLED', False) else 404


@bp.route('/api/pages')
def page_list():
    """The pages this account may open now, for "Go to" (Ctrl+K) on every page (issue #250)."""
    ctx = {}
    # The same context the floor plan's top bar is drawn with: features, permissions, set-up flags.
    current_app.update_template_context(ctx)
    return jsonify({'pages': page_index.for_context(ctx)})


@bp.route('/api/pages/find')
def find_place():
    """Seats and switches for "Go to" as you type (issue #252): ``?q=b8`` finds seat B-8."""
    q = request.args.get('q', '')[:100]
    found = page_index.places(q)
    # Players by nick, IP or MAC, like the floor plan's own search, for those who may see people
    # (issue #292). Seat numbers alone are already in the list above.
    if len(q.strip()) >= 2 and _can('seats.view'):
        found += [{'kind': 'player', 'name': f"{r['nick'] if r['matched'] == 'nick' else q.strip()} · {r['seat']}",
                   'href': f"/plan?seat={quote(r['seat'])}"}
                  for r in seat_view.find_player(q)['results'] if r['matched'] != 'seat'][:5]
    return jsonify({'places': found})


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))
