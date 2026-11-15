"""The HTML pages of the editor and the kiosk view, and the list of pages for "Go to"."""
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, render_template, request

from .. import nav, page_index, seat_view

bp = Blueprint('pages', __name__)


@bp.app_context_processor
def nav_context():
    # The sidebar on every crew page (templates/_nav.html).
    return nav.context()


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/kiosk')
def kiosk():
    """Read-only floor plan for a big screen (see docs/kiosk.md)."""
    return render_template('kiosk.html')


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
