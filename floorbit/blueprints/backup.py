"""Backup and restore of the floor plan and settings (Settings > Backup).

A backup holds what took work to set up: the halls with their background images, the inventory
(devices and where they are placed), seat blocks and the saved settings, including the theme and
event logo. It never holds secrets (API tokens, webhook URLs, the session key) or accounts, so it is
safe to keep on a laptop or share with another orga team, and restoring one can't lock anybody out.
Check-ins are personal data and stay out too.
For a full copy of everything, back up the ``data.json`` file itself. See docs/backup.md.
"""
import time

from flask import Blueprint, Response, current_app, jsonify, request

from .. import halls, inventory, runtime, store
from ..settings import FIELDS_BY_KEY, check_changes

bp = Blueprint('backup', __name__)

FORMAT = 'floorbit-backup'
FORMAT_VERSION = 1
# The parts of data.json a backup carries. Everything else (accounts, the session key) stays put.
LAYOUT_KEYS = ('halls', 'inventory', 'seats', 'seat_blocks')
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
                   'halls': [{'id': h['id'], 'name': h['name'], 'background': halls.background_data_url(h)}
                             for h in halls.halls(data)]},
        'settings': settings,
    }


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
            out.append(({'id': hid, 'name': halls.clean_name(raw['name']), 'background': None}, image))
        except halls.HallError as exc:
            raise BackupError(f'Hall "{hid}": {exc}') from None
    return out


def validate(backup):
    """Check a backup's shape before anything is written. Returns (layout, settings)."""
    if not isinstance(backup, dict) or backup.get('format') != FORMAT:
        raise BackupError('This is not a Floorbit backup file')
    if backup.get('version') != FORMAT_VERSION:
        raise BackupError(f'Backup format {backup.get("version")!r} is not supported (expected {FORMAT_VERSION})')
    layout, settings = backup.get('layout'), backup.get('settings')
    if not isinstance(layout, dict) or not isinstance(settings, dict):
        raise BackupError('The backup has no "layout" or "settings" section')
    unknown = sorted(set(layout) - set(LAYOUT_KEYS) - set(OLD_LAYOUT_KEYS))
    if unknown:
        raise BackupError(f'Unknown layout part(s): {", ".join(unknown)}')
    for key in ('switches', 'cached_devices', 'seat_blocks'):
        if key in layout:
            _check_list(key, layout[key])
    if 'inventory' in layout:
        _check_list('inventory', layout['inventory'], required=('id', 'name'))
        try:
            layout['inventory'] = [inventory.normalize(d) for d in layout['inventory']]
        except inventory.InventoryError as exc:
            raise BackupError(f'An inventory entry is not valid: {exc}') from None
    if 'seats' in layout:
        _check_list('seats', layout['seats'], required=())
    if 'halls' in layout:
        layout['halls'] = _check_halls(layout['halls'])
    if 'positions' in layout and not isinstance(layout['positions'], dict):
        raise BackupError('"positions" must be an object')
    return layout, settings


def restore(data, backup, settings_store):
    """Apply a validated backup to ``data`` (the loaded data.json) and save it.

    Layout parts are replaced; parts the backup lacks are emptied, so the result matches the
    backup. Settings are validated like a save from the settings page; secrets and settings the
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
    data['inventory'] = parts['inventory']
    for key in OLD_LAYOUT_KEYS:
        data.pop(key, None)
    for key in ('seats', 'seat_blocks'):
        data[key] = layout.get(key, [])
    for hall in halls.halls(data):
        halls.remove_background(hall)
    data['halls'] = []
    for hall, image in layout.get('halls') or []:
        if image:
            halls.set_background(hall, *image)
        data['halls'].append(hall)
    store.save_data(data)
    if settings:
        settings_store.update(settings)
    runtime.apply(settings_store)
    return {
        'restored': {'inventory': len(data['inventory']), 'halls': len(halls.halls(data)),
                     **{k: len(layout.get(k, [])) for k in ('seats', 'seat_blocks')}},
        'settings': len(settings),
        'skipped_settings': skipped,
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
