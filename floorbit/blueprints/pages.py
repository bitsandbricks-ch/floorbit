"""The HTML pages of the editor, old links that moved, and the list of pages for "Go to"."""
from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, redirect, request

from .. import endpoints, nav, nav_sections, page_index, seat_view, spa

bp = Blueprint('pages', __name__)


@bp.app_context_processor
def nav_context():
    # The sidebar on every crew page (templates/_nav.html).
    return nav.context()


@bp.route('/')
def index():
    """The floor plan is the React workspace now (``/plan``); its editor does what this page's
    editor did. Old links (``/?hall=``, ``/?seat=``, ``/?switch=`` from Problems and incidents) open
    there, editing for an account that may edit, since they meant "show it in the editor"."""
    from auth import current_user, roles
    args = request.args.to_dict()
    user = current_user()
    if args and user and roles.can(user, 'floorplan.edit'):
        args.setdefault('edit', '1')
    return redirect('/plan' + (f'?{urlencode(args)}' if args else ''))


@bp.route('/editor/classic')
def classic_editor():
    """The older editor is retired (Mike: not kept in sync); bookmarks open the plan's editor on the
    same hall."""
    hall = request.args.get('hall')
    return redirect('/plan?' + urlencode({'edit': '1', **({'hall': hall} if hall else {})}))


@bp.route('/kiosk')
def kiosk():
    """The old big-screen page is the ready-made Kiosk dashboard now (docs/kiosk.md). Screens that
    still open /kiosk land there, on the same hall and theme; ``?view=heat`` opens the plan's traffic view."""
    keep = {k: request.args[k] for k in ('hall', 'theme') if request.args.get(k)}
    if request.args.get('view') == 'heat':
        return redirect('/plan?' + urlencode({'screen': '1', 'layers': 'marks,status', **keep}))
    return redirect('/dashboards/kiosk' + (f'?{urlencode(keep)}' if keep else ''))


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
    pages = page_index.for_context(ctx)
    # Plugin pages (plugin.yaml ``pages:``) go into the sidebar's Plugins group.
    from .plugins import _language, plugin_pages
    pages += plugin_pages(_language())
    # The sections admins made (floorbit/nav_sections.py), with only the links this account may open.
    return jsonify({'pages': pages, 'custom': nav_sections.for_pages(pages)})


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
        # An IP or MAC (or its start): where it was seen, from the history (floorbit/endpoints.py).
        if endpoints.looks_like_address(q):
            found += _endpoint_places(q)
    return jsonify({'places': found})


def _endpoint_places(q):
    from ..database import DatabaseError
    try:
        rows = endpoints.history().search(q, limit=20)
    except DatabaseError:
        return []
    out, seen = [], set()
    for r in rows:
        key = (r['mac'], r['ip'])
        if key in seen:
            continue
        seen.add(key)
        where = r['seat'] or ' '.join(x for x in (r['device'], r['port']) if x)
        out.append({'kind': 'endpoint', 'name': f"{r['ip'] or r['mac']} · {where}",
                    'href': f"/endpoints?q={quote(r['ip'] or r['mac'])}"})
    return out[:5]


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))
