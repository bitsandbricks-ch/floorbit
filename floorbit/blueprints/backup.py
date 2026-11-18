"""Backup and restore of the floor plan and settings (Settings > Backup).

A backup holds what took work to set up: the halls with their background images, the inventory
(devices and where they are placed), seat blocks, the cabling (cables, their drawn routes, patch
panels, uplinks between switches, port areas), the power boards and circuits, and the saved
settings, including the theme and event logo. It never holds secrets (API tokens, webhook URLs,
the session key) or accounts, so it is safe to keep on a laptop or share with another orga team,
and restoring one can't lock anybody out. Check-ins are personal data and stay out too.
For a full copy of everything, back up the ``data.json`` file itself. See docs/backup.md.
"""
import math
import re
import time

from flask import Blueprint, Response, current_app, jsonify, request

from .. import cable_plan, cables, halls, inventory, links, plan_marks, port_areas, power, runtime, store
from ..settings import FIELDS_BY_KEY, check_changes
from . import seat_blocks

bp = Blueprint('backup', __name__)

FORMAT = 'floorbit-backup'
FORMAT_VERSION = 1
# The parts of data.json a backup carries. Everything else (accounts, the session key) stays put.
LAYOUT_KEYS = ('halls', 'inventory', 'seats', 'seat_blocks', 'plan_marks', 'plan_groups')
# The cabling and power drawn on the plan. A backup from before these were in it doesn't name them:
# restoring it leaves them as they are (and says so) instead of emptying them.
PLAN_KEYS = ('patch_panels', 'links', 'cables', 'cable_routes', 'power', 'port_areas')
PLAN_EMPTY = {'patch_panels': list, 'links': list, 'cables': list, 'cable_routes': dict,
              'power': lambda: {'boards': [], 'circuits': []}, 'port_areas': list}
ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$')
# Backups from before the inventory: still restored, moved over like data.json is.
OLD_LAYOUT_KEYS = ('switches', 'cached_devices', 'positions')
MAX_BYTES = 64 * 1024 * 1024   # background images travel inline, up to 5 MB each


class BackupError(ValueError):
    pass


def _secret_keys():
    # Integrations add their fields at start-up, so look the secrets up at call time.
    return {k for k, f in FIELDS_BY_KEY.items() if f['type'] == 'secret'}


def make_backup(data):
    inventory.migrate(data)
    secrets = _secret_keys()
    settings = {k: v for k, v in (data.get('app_settings') or {}).items()
                if k in FIELDS_BY_KEY and k not in secrets}
    return {
        'format': FORMAT,
        'version': FORMAT_VERSION,
        'created': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'layout': {**{k: data[k] for k in LAYOUT_KEYS if k in data and k != 'halls'},
                   'halls': [_hall_out(h) for h in halls.halls(data)],
                   # Always written, empty or not: an empty part restores as empty, not as "kept".
                   **{k: data[k] if k in data else PLAN_EMPTY[k]() for k in PLAN_KEYS}},
        'settings': settings,
    }


def _hall_out(h):
    # Where the background sits and the hall's scale go with it (missing: the whole plan, no scale).
    bg = h.get('background') or {}
    extra = {'frame': bg.get('frame'), 'opacity': bg.get('opacity'), 'seat_m': h.get('seat_m')}
    return {'id': h['id'], 'name': h['name'], 'background': halls.background_data_url(h),
            **{k: v for k, v in extra.items() if v is not None}}


def _check_list(name, value, required=('id',)):
    if not isinstance(value, list) or not all(isinstance(i, dict) for i in value):
        raise BackupError(f'"{name}" must be a list of objects')
    for item in value:
        missing = [k for k in required if k not in item]
        if missing:
            raise BackupError(f'An entry in "{name}" has no {", ".join(missing)}')


def _check_halls(value):
    """[(hall, (mime, bytes) or None)], every image decoded before anything is written."""
    _check_list('halls', value, required=('id', 'name'))
    if len(value) > halls.MAX_HALLS:
        raise BackupError(f'At most {halls.MAX_HALLS} halls')
    out, seen = [], set()
    for raw in value:
        hid = str(raw['id'])[:40]
        if not hid.replace('-', '').replace('_', '').isalnum() or hid in seen:
            raise BackupError(f'Hall id "{hid}" is not valid or used twice')
        seen.add(hid)
        try:
            image = halls.decode_image(raw['background']) if raw.get('background') else None
            hall = {'id': hid, 'name': halls.clean_name(raw['name']), 'background': None}
            halls.set_scale(hall, raw.get('seat_m'))
            # Checked now on a stand-in, put on the background once it is written.
            place = {k: raw[k] for k in ('frame', 'opacity') if raw.get(k) is not None}
            halls.place_background({'background': {'stand-in': True}}, place)
            out.append((hall, image, place))
        except halls.HallError as exc:
            raise BackupError(f'Hall "{hid}": {exc}') from None
    return out


# Seat blocks and marks are drawn by nearly every page: one bad entry restored as it is would turn
# the plan, the incidents and the problems into errors for everybody. They get the editor's checks.
def _seat_block(raw):
    try:
        return seat_blocks.check(raw)
    except seat_blocks.BlockError as exc:
        raise BackupError(f'Seat block "{raw["id"]}": {exc}') from None
    except (KeyError, TypeError, ValueError):
        raise BackupError(f'Seat block "{raw["id"]}": its position or size is not a number') from None


def _plan_mark(raw):
    try:
        mark = plan_marks.clean(raw, old={'id': str(raw['id'])})
    except plan_marks.MarkError as exc:
        raise BackupError(f'Plan mark "{raw["id"]}": {exc}') from None
    if 'hall_id' in raw:
        mark['hall_id'] = raw['hall_id']
    return mark


def validate(backup):
    """Check a backup's shape before anything is written. Returns (layout, settings)."""
    if not isinstance(backup, dict) or backup.get('format') != FORMAT:
        raise BackupError('This is not a Floorbit backup file')
    if backup.get('version') != FORMAT_VERSION:
        raise BackupError(f'Backup format {backup.get("version")!r} is not supported (expected {FORMAT_VERSION})')
    layout, settings = backup.get('layout'), backup.get('settings')
    if not isinstance(layout, dict) or not isinstance(settings, dict):
        raise BackupError('The backup has no "layout" or "settings" section')
    unknown = sorted(set(layout) - set(LAYOUT_KEYS) - set(OLD_LAYOUT_KEYS) - set(PLAN_KEYS))
    if unknown:
        raise BackupError(f'Unknown layout part(s): {", ".join(unknown)}')
    for key in ('switches', 'cached_devices', 'seat_blocks', 'plan_marks', 'plan_groups'):
        if key in layout:
            _check_list(key, layout[key])
    if 'inventory' in layout:
        _check_list('inventory', layout['inventory'], required=('id', 'name'))
        try:
            layout['inventory'] = [inventory.normalize(d) for d in layout['inventory']]
        except inventory.InventoryError as exc:
            raise BackupError(f'An inventory entry is not valid: {exc}') from None
    if 'seat_blocks' in layout:
        layout['seat_blocks'] = [_seat_block(b) for b in layout['seat_blocks']]
    if 'plan_marks' in layout:
        layout['plan_marks'] = [_plan_mark(m) for m in layout['plan_marks']]
    if 'seats' in layout:
        _check_list('seats', layout['seats'], required=())
    if 'halls' in layout:
        layout['halls'] = _check_halls(layout['halls'])
    if 'positions' in layout and not isinstance(layout['positions'], dict):
        raise BackupError('"positions" must be an object')
    for key, limit in (('patch_panels', cable_plan.MAX_PANELS), ('links', links.MAX_LINKS),
                       ('cables', cables.MAX_CABLES), ('port_areas', port_areas.MAX_AREAS)):
        if key in layout:
            _check_list(key, layout[key], required=('name',) if key == 'patch_panels' else ('id',))
            if len(layout[key]) > limit:
                raise BackupError(f'At most {limit} entries in "{key}"')
    if 'cable_routes' in layout and not isinstance(layout['cable_routes'], dict):
        raise BackupError('"cable_routes" must be an object')
    if 'power' in layout:
        board = layout['power']
        if not isinstance(board, dict):
            raise BackupError('"power" must be an object')
        _check_list('power boards', board.get('boards', []))
        _check_list('power circuits', board.get('circuits', []))
    return layout, settings


# ── Cabling and power ─────────────────────────────────────────────────────────
# Checked with the editor's own rules against the floor plan being restored (its switches, seat
# blocks, halls and panels), not the current one: a cable to a panel that only the backup has is fine.
def _id(raw, key):
    value = str(raw.get('id') or '')
    if not ID_RE.match(value):
        raise BackupError(f'An entry in "{key}" has no valid id')
    return value


def _when(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _who(value):
    return str(value)[:80] if isinstance(value, str) else None


def _unique(rows, key):
    seen = set()
    for row in rows:
        if row['id'] in seen:
            raise BackupError(f'The id "{row["id"]}" is in "{key}" twice')
        seen.add(row['id'])
    return rows


def _panels(value, view):
    out, seen = [], set()
    for raw in value:
        name = ' '.join(str(raw.get('name') or '').split())
        if name.lower() in seen:
            raise BackupError(f'Patch panel "{name}" is in the backup twice')
        seen.add(name.lower())
        try:
            if not cable_plan.PANEL_RE.match(name):
                raise cable_plan.RouteError('A patch panel name is up to 40 letters, digits, spaces, . _ / # or -.')
            try:
                x, y = (float(raw.get(k)) for k in ('x', 'y'))
            except (TypeError, ValueError, OverflowError):
                x = y = math.nan
            if not (math.isfinite(x) and math.isfinite(y) and abs(x) <= 1000 and abs(y) <= 1000):
                raise cable_plan.RouteError('A patch panel position is a point on the plan in percent.')
            ports = cable_plan._panel_ports(raw.get('ports') or cable_plan.PANEL_PORTS)
            hall = halls.check_id(view, raw.get('hall_id'))
        except (cable_plan.RouteError, halls.HallError) as exc:
            raise BackupError(f'Patch panel "{name[:40]}": {exc}') from None
        out.append({'name': name, 'x': round(x, 2), 'y': round(y, 2), 'hall_id': hall, 'ports': ports})
    return out


def _links(value, view):
    out = []
    for raw in value:
        lid = _id(raw, 'links')
        try:
            link = links._clean(raw, view)
        except links.LinkError as exc:
            raise BackupError(f'Link "{lid}": {exc}') from None
        mine = links._ends(link)
        clash = next((x for x in out if links._ends(x) & mine), None)
        if clash:
            raise BackupError(f'Link "{lid}": link "{clash["id"]}" already uses one of its ports')
        out.append({'id': lid, **link, 'updated_at': _when(raw.get('updated_at')), 'by': _who(raw.get('by'))})
    return _unique(out, 'links')


def _cables(value, panels):
    out = []
    for raw in value:
        cid = _id(raw, 'cables')
        try:
            cable = cables.clean(raw, out, panels=panels)
        except cables.CableError as exc:
            raise BackupError(f'Cable "{raw.get("label") or cid}": {exc}') from None
        source = 'import' if raw.get('source') == 'import' else 'floorbit'
        extra = {'plugin': _who(raw['plugin'])} if source == 'import' and raw.get('plugin') else {}
        out.append({'id': cid, **cable, 'source': source, **extra,
                    'updated_at': _when(raw.get('updated_at')), 'by': _who(raw.get('by'))})
    return _unique(out, 'cables')


def _routes(value):
    if len(value) > cable_plan.MAX_ROUTES:
        raise BackupError(f'At most {cable_plan.MAX_ROUTES} cable drawings')
    out = {}
    for key, raw in value.items():
        try:
            if not isinstance(key, str) or not cable_plan.KEY_RE.match(key) or not isinstance(raw, dict):
                raise cable_plan.RouteError('That is not a cable on the plan.')
            corners = raw.get('corners') or 'square'
            if corners not in cable_plan.CORNERS:
                raise cable_plan.RouteError('A cable is drawn straight, angled or rounded.')
            points = cable_plan._clean_points(raw.get('points'))
        except cable_plan.RouteError as exc:
            raise BackupError(f'Cable drawing "{str(key)[:80]}": {exc}') from None
        out[key] = {'points': points, 'corners': corners, 'by': _who(raw.get('by')), 'at': _when(raw.get('at'))}
    return out


def _power(value, view):
    boards, circuits = [], []
    if len(value.get('boards') or []) > power.MAX_BOARDS or len(value.get('circuits') or []) > power.MAX_CIRCUITS:
        raise BackupError(f'At most {power.MAX_BOARDS} power boards and {power.MAX_CIRCUITS} circuits')
    for raw in value.get('boards') or []:
        bid = _id(raw, 'power boards')
        try:
            boards.append(power._clean_board(raw, old={'id': bid}))
        except power.PowerError as exc:
            raise BackupError(f'Power board "{raw.get("name") or bid}": {exc}') from None
    for raw in value.get('circuits') or []:
        cid = _id(raw, 'power circuits')
        try:
            # Tripped and the last reading are the event's live state, not its setup.
            circuits.append(power._clean_circuit(raw, view, boards, old={'id': cid}))
        except power.PowerError as exc:
            raise BackupError(f'Power circuit "{raw.get("name") or cid}": {exc}') from None
        except (TypeError, ValueError):
            raise BackupError(f'Power circuit "{raw.get("name") or cid}": its seat blocks or switches are not lists') \
                from None
    return {'boards': _unique(boards, 'power boards'), 'circuits': _unique(circuits, 'power circuits')}


def _areas(value):
    out = []
    for raw in value:
        aid = _id(raw, 'port_areas')
        switch = ' '.join(str(raw.get('switch') or '').split())[:80]
        first, last, seats = raw.get('first'), raw.get('last'), raw.get('seats')
        if not switch or not all(isinstance(n, int) and not isinstance(n, bool) for n in (first, last)) \
                or not 0 <= first <= last <= 100000 or not isinstance(seats, list) \
                or not 0 < len(seats) <= port_areas.MAX_PORTS or not all(isinstance(x, str) for x in seats):
            raise BackupError(f'Port area "{aid}": it needs a switch, its first and last port and its seats')
        area = {'switch': switch, 'first': first, 'last': last, 'seats': [x.strip().upper()[:16] for x in seats]}
        out.append({'id': aid, **area, 'label': port_areas._label(area),
                    'updated_at': _when(raw.get('updated_at')), 'by': _who(raw.get('by'))})
    return _unique(out, 'port_areas')


def check_plan(layout, view, current_panels):
    """The backup's cabling and power, checked against ``view`` (the restored inventory, seat blocks
    and halls). Returns {key: value} for the parts the backup has."""
    out = {}
    if 'patch_panels' in layout:
        out['patch_panels'] = _panels(layout['patch_panels'], view)
    if 'links' in layout:
        out['links'] = _links(layout['links'], view)
    if 'cables' in layout:
        # Without its panels in the backup, a cable's panel port is checked against the current ones.
        panels = out.get('patch_panels')
        out['cables'] = _cables(layout['cables'], panels if panels is not None else
                                current_panels)
    if 'cable_routes' in layout:
        out['cable_routes'] = _routes(layout['cable_routes'])
    if 'power' in layout:
        out['power'] = _power(layout['power'], view)
    if 'port_areas' in layout:
        out['port_areas'] = _areas(layout['port_areas'])
    return out


def restore(data, backup, settings_store):
    """Apply a validated backup to ``data`` (the loaded data.json) and save it.

    Layout parts are replaced; parts the backup lacks are emptied, so the result matches the
    backup. The cabling and power parts (``PLAN_KEYS``) are replaced too, as a whole; a backup from
    before they were in it leaves them as they are, and the result lists them under ``kept``.
    Settings are validated like a save from the settings page; secrets and settings the
    backup doesn't name keep their current value.
    """
    layout, settings = validate(backup)
    secrets = _secret_keys()
    settings = {k: v for k, v in settings.items() if k in FIELDS_BY_KEY and k not in secrets}
    skipped = sorted(k for k in backup['settings'] if k not in settings)
    check_changes(settings)   # a bad value stops the restore before anything is written

    parts = {k: layout[k] for k in (*OLD_LAYOUT_KEYS, 'inventory') if k in layout}
    if 'inventory' in parts:
        for key in OLD_LAYOUT_KEYS:
            parts.pop(key, None)
    inventory.migrate(parts)
    hall_rows = [hall for hall, _, _ in layout.get('halls') or []]
    view = {'inventory': parts['inventory'], 'seat_blocks': layout.get('seat_blocks', []), 'halls': hall_rows}
    plan = check_plan(layout, view, cable_plan.panels(data))   # before anything below changes data or removes an image
    kept = [k for k in PLAN_KEYS if k not in plan]

    data['inventory'] = parts['inventory']
    for key in OLD_LAYOUT_KEYS:
        data.pop(key, None)
    for key in ('seats', 'seat_blocks', 'plan_marks', 'plan_groups'):
        data[key] = layout.get(key, [])
    for hall in halls.halls(data):
        halls.remove_background(hall)
    data['halls'] = []
    for hall, image, place in layout.get('halls') or []:
        if image:
            halls.set_background(hall, *image)
            halls.place_background(hall, place)
        data['halls'].append(hall)
    data.update(plan)
    store.save_data(data)
    if settings:
        settings_store.update(settings)
    runtime.apply(settings_store)
    return {
        'restored': {'inventory': len(data['inventory']), 'halls': len(halls.halls(data)),
                     **{k: len(layout.get(k, [])) for k in ('seats', 'seat_blocks')},
                     **{k: len(plan[k]) for k in ('cables', 'links', 'patch_panels', 'port_areas') if k in plan}},
        'settings': len(settings),
        'skipped_settings': skipped,
        'kept': kept,
    }


@bp.route('/api/settings/backup', methods=['GET'])
def download_backup():
    body = current_app.json.dumps(make_backup(store.load_data()), indent=2)
    filename = f"floorbit-backup-{time.strftime('%Y%m%d-%H%M')}.json"
    return Response(body + '\n', mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"',
                             'Cache-Control': 'no-store'})


@bp.route('/api/settings/backup', methods=['POST'])
def restore_backup():
    if (request.content_length or 0) > MAX_BYTES:
        return jsonify({'error': f'A backup is at most {MAX_BYTES // (1024 * 1024)} MB'}), 413
    backup = request.get_json(silent=True)
    if backup is None:
        return jsonify({'error': 'Send the backup file as JSON'}), 400
    settings_store = current_app.extensions['floorbit_settings']
    try:
        result = restore(store.load_data(), backup, settings_store)
    except BackupError as exc:
        return jsonify({'error': str(exc)}), 400
    except ValueError as exc:   # SettingsError from a bad setting value
        return jsonify({'error': f'A setting in the backup is not valid: {exc}'}), 400
    return jsonify(result)
