"""Backups in an S3 bucket (Settings > Backup and restore). See floorbit/s3_backup.py, docs/backup.md.

Under /api/settings, so only accounts with settings.manage reach it, and every POST is in the audit log.
"""
from flask import Blueprint, Response, current_app, g, jsonify, request

from .. import s3_backup, store
from . import backup

bp = Blueprint('s3_backup', __name__)


def _error(exc, status=502):
    return jsonify({'error': str(exc)}), status


@bp.route('/api/settings/backup/s3', methods=['GET'])
def overview():
    """The schedule, the last run and the backups in the bucket."""
    info = {'configured': s3_backup.configured(), 'interval_hours': s3_backup.interval_hours(),
            'keep': s3_backup.keep(), **{k: v for k, v in s3_backup.state().items() if k in ('last', 'last_ok')}}
    if not info['configured']:
        return jsonify({**info, 'backups': []})
    s = s3_backup.settings()
    info.update(bucket=s['bucket'], prefix=s['prefix'], encrypted=bool(s['passphrase']))
    try:
        info['backups'] = s3_backup.listing(s)
    except s3_backup.S3Error as exc:
        info.update(backups=[], error=str(exc))
    return jsonify(info)


@bp.route('/api/settings/backup/s3', methods=['POST'])
def upload_now():
    try:
        return jsonify(s3_backup.run(g.get('audit_user') or 'admin'))
    except s3_backup.S3Error as exc:
        return _error(exc, 400 if not s3_backup.configured() else 502)


def _key():
    body = request.get_json(silent=True)
    return body.get('key') if isinstance(body, dict) else request.args.get('key')


@bp.route('/api/settings/backup/s3/restore', methods=['POST'])
def restore():
    try:
        found = s3_backup.fetch(_key())
        result = backup.restore(store.load_data(), found, current_app.extensions['floorbit_settings'])
    except s3_backup.S3Error as exc:
        return _error(exc, 400)
    except backup.BackupError as exc:
        return _error(exc, 400)
    except ValueError as exc:   # SettingsError from a bad setting value
        return jsonify({'error': f'A setting in the backup is not valid: {exc}'}), 400
    return jsonify(result)


@bp.route('/api/settings/backup/s3/download', methods=['GET'])
def download():
    """One backup from the bucket, opened, as the JSON file Restore from file takes."""
    try:
        found = s3_backup.fetch(request.args.get('key'))
    except s3_backup.S3Error as exc:
        return _error(exc, 400)
    name = str(request.args.get('key')).rsplit('/', 1)[-1].split('.json')[0] + '.json'
    body = current_app.json.dumps(found, indent=2)
    return Response(body + '\n', mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="{name}"', 'Cache-Control': 'no-store'})

