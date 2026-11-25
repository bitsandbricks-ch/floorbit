"""Dashboards: screens split into panes (floorbit/dashboards.py, docs/dashboards.md).

- ``GET /dashboards``: the list and the editor; ``GET /dashboards/<id>``: one dashboard full screen.
- ``GET /api/dashboards``, ``GET /api/dashboards/<id>``: everyone who sees the floor plan.
- ``PUT``/``DELETE /api/dashboards/<id>``: floorplan.edit (auth/roles.py).
- ``GET /api/widgets``: the saved widgets, with the dashboards that show each; ``POST /api/widgets`` and
  ``PUT``/``DELETE /api/widgets/<id>``: floorplan.edit, like the dashboards (floorbit/saved_widgets.py).
- ``GET /api/dashboards/<id>/export``: the dashboard as a file for another Floorbit, for whoever may open
  it; ``POST /api/dashboards/import``: such a file as a new dashboard, floorplan.edit (#938).
- ``GET /api/dashboards/<id>/public`` and its ``/plan`` and ``/tiles/<tile>``: a public dashboard for a
  screen nobody signed in to, trimmed to what anyone may see (dashboards.public_board). Open to all.
"""
import json
from collections import Counter

from flask import Blueprint, abort, current_app, g, jsonify, redirect, request, url_for

from auth import current_user, public_endpoint, roles

from .. import audit, dashboards, saved_widgets, seat_view, spa

bp = Blueprint('dashboards', __name__)


def _error(message, status=400):
    return jsonify({'error': message}), status


@bp.route('/dashboards')
def dashboards_page():
    return spa.render('Dashboards')


@bp.route('/widgets')
def widgets_page():
    # The widget gallery: what each widget shows comes from its own API, so the page holds no data.
    return spa.render('Widgets')


@bp.route('/dashboards/<layout_id>')
@public_endpoint
def dashboard_screen(layout_id):
    # The page holds no data. A public dashboard opens for anyone; the rest asks for an account as usual.
    layout = dashboards.get(layout_id)
    if not (layout and layout.get('public')) and current_app.extensions['auth'].enabled:
        user = current_user()
        if not user:
            return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))
        if not roles.can(user, 'floorplan.view'):
            abort(403)
        if not dashboards.may_open(user, layout_id):
            return redirect(f"/dashboards/{user['dashboards'][0]}")
    return spa.render('Dashboard')


def _public(layout_id):
    layout = dashboards.get(layout_id)
    return layout if layout and layout.get('public') else None


def _signed_in():
    return not current_app.extensions['auth'].enabled or current_user() is not None


@bp.route('/api/dashboards/<layout_id>/public')
@public_endpoint
def public_layout(layout_id):
    """``account``: this browser is signed in (or sign-in is off), so the screen reads the full dashboard."""
    from .plugins import _lang, core
    layout = _public(layout_id)
    # The tiles' names in the browser's language: the full tile list (/api/dashboard) needs an account.
    names = {f"floorbit/w/{t['id']}": t['label'] for t in core.tiles(_lang(), False)}
    return jsonify({'account': _signed_in(), 'board': dashboards.public_board(layout) if layout else None,
                    'tiles': {k: names[k] for k in dashboards.PUBLIC_TILES if k in names},
                    # The running version, so a public screen reloads after an update without /api/version.
                    'app': current_app.config.get('FLOORBIT_VERSION') or '0'})


@bp.route('/api/dashboards/<layout_id>/public/plan')
@public_endpoint
def public_plan(layout_id):
    layout = _public(layout_id)
    plans = [p for p in dashboards.public_panes(layout) if p['kind'] == 'plan'] if layout else []
    hall = request.args.get('hall') or ''
    # A pane without a hall shows the first one, or rotates through all of them.
    if not plans or not (hall in {p['hall'] for p in plans} or any(not p['hall'] for p in plans)):
        return _error('No such dashboard.', 404)
    return jsonify(seat_view.public_view(hall or None))


@bp.route('/api/dashboards/<layout_id>/public/tiles/<tile>')
@public_endpoint
def public_tile(layout_id, tile):
    from ..plugins.widgets import check_widget
    from .plugins import CORE_TILES, core
    layout = _public(layout_id)
    key = f'floorbit/w/{tile}'
    if not layout or key not in dashboards.PUBLIC_TILES \
            or not any(key in dashboards.pane_tiles(p) for p in dashboards.public_panes(layout)):
        return _error('No such dashboard.', 404)
    spec = core.TILES[tile]
    # No "Details" link: the pages it opens need an account.
    widget = check_widget({**CORE_TILES[tile](None), 'link': ''},
                          {'id': tile, 'label': '', 'size': spec['size'], 'refresh': spec['refresh']})
    # Nor which device a row is: inventory ids are crew data.
    for item in widget.get('items') or []:
        item.pop('device', None)
    return jsonify(widget)


@bp.route('/api/dashboards', methods=['GET'])
def list_layouts():
    # A screen account limited to some dashboards (Settings > Users) sees only those.
    allowed = dashboards.allowed_for(current_user())
    layouts = _plugin_names([x for x in dashboards.all_layouts() if allowed is None or x['id'] in allowed])
    if allowed is None:
        # How many screen accounts show each one (#897), for "Shows on" in the list. A count, no names.
        screens = Counter(i for u in _accounts() for i in u.get('dashboards') or [])
        layouts = [{**x, 'screens': screens[x['id']]} if screens[x['id']] else x for x in layouts]
    return jsonify({'layouts': layouts, 'limited': allowed is not None})


def _accounts():
    auth = current_app.extensions['auth']
    return auth.users.list() if auth.enabled else []


@bp.route('/api/dashboards/<layout_id>', methods=['GET'])
def get_layout(layout_id):
    layout = dashboards.get(layout_id)
    # A limited screen account still opens a public one, as anyone could without signing in.
    if not layout or not (layout.get('public') or dashboards.may_open(current_user(), layout_id)):
        return _error('No such dashboard.', 404)
    return jsonify(layout)


def _plugin_names(layouts):
    """Plugin dashboards' names in the reader's language, from the plugin's own texts."""
    from .. import i18n
    registry = current_app.extensions['floorbit_plugins']
    lang = i18n.language(request.headers.get('Accept-Language'))
    out = []
    for x in layouts:
        spec = registry.specs.get(x.get('plugin')) if x.get('builtin') else None
        out.append({**x, 'name': registry.text(spec, x['name'], lang)} if spec else x)
    return out


@bp.route('/api/dashboards/<layout_id>/export', methods=['GET'])
def export_layout(layout_id):
    layout = dashboards.get(layout_id)
    if not layout or not dashboards.may_open(current_user(), layout_id):
        return _error('No such dashboard.', 404)
    from .. import downloads
    body = json.dumps(dashboards.export(layout), indent=2, ensure_ascii=False)
    return current_app.response_class(body, mimetype='application/json', headers={
        'Content-Disposition': downloads.disposition(f'{layout_id}.dashboard.json')})


@bp.route('/api/dashboards/import', methods=['POST'])
def import_layout():
    user = g.get('audit_user')
    try:
        layout = dashboards.import_file(request.get_json(silent=True), user)
    except dashboards.LayoutError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Imported dashboard', user, layout['name'])
    # The plugins its tiles come from that are not on here: the screen says so on each pane.
    registry = current_app.extensions['floorbit_plugins']
    on = {s.id for s in registry.specs.values() if registry.enabled(s)} | {'floorbit'}
    needs = sorted({t.split('/w/')[0] for p in dashboards.layout_panes(layout)
                    for t in dashboards.pane_tiles(p)} - on)
    return jsonify({'layout': layout, 'missing': needs}), 201


@bp.route('/api/dashboards/<layout_id>', methods=['PUT'])
def save_layout(layout_id):
    user = g.get('audit_user')
    try:
        layout = dashboards.save(layout_id, request.get_json(silent=True), user)
    except dashboards.LayoutError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Saved dashboard', user, layout['name'])
    return jsonify(layout)


@bp.route('/api/dashboards/<layout_id>', methods=['DELETE'])
def delete_layout(layout_id):
    try:
        dashboards.delete(layout_id)
    except dashboards.LayoutError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Removed dashboard', g.get('audit_user'), layout_id)
    return jsonify({'ok': True})


@bp.route('/api/widgets', methods=['GET'])
def list_widgets():
    from ..store import load_data
    data = load_data()
    return jsonify({'widgets': [{**w, 'used_on': saved_widgets.used_on(w['id'], data)}
                                for w in saved_widgets.all_widgets(data)]})


@bp.route('/api/widgets', methods=['POST'])
@bp.route('/api/widgets/<widget_id>', methods=['PUT'])
def save_widget(widget_id=None):
    user = g.get('audit_user')
    try:
        widget = saved_widgets.save(widget_id, request.get_json(silent=True), user)
    except saved_widgets.WidgetError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Saved widget', user, widget['name'])
    return jsonify(widget), 200 if widget_id else 201


@bp.route('/api/widgets/<widget_id>', methods=['DELETE'])
def delete_widget(widget_id):
    try:
        saved_widgets.delete(widget_id)
    except saved_widgets.WidgetError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Removed widget', g.get('audit_user'), widget_id)
    return jsonify({'ok': True})
