"""The seat mapping page and API (floorbit/seatmap.py has the rules).

Personal data (nicks, IPs, MACs), so everything here is editors and up, never public, whatever
AUTH_PUBLIC_READ says (auth/roles.py EDITOR_PATHS).

- ``GET /api/seat-map``: the merged mapping, which source gave each field, the hand entries.
- ``PUT /api/seat-map/<seat>``: set a seat's hand entry (``ip``, ``mac``, ``nick``, ``note``).
- ``DELETE /api/seat-map/<seat>``: drop the hand entry; the other sources show again.
- ``GET /api/seat-map.csv``: the hand entries as CSV.
- ``POST /api/seat-map/import``: CSV (``{"csv": "...", "replace": false, "dry_run": true}``),
  every row checked before anything is written.
"""
import time

from flask import Blueprint, Response, jsonify, request

from integrations import seat_sources

from .. import seatmap, spa
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('seat_map', __name__)


def _user():
    try:
        from auth import current_user
        return (current_user() or {}).get('username')
    except Exception:  # noqa: BLE001  # sign-in switched off or not set up
        return None


def _merged():
    seat_sources.invalidate()
    merged = seat_sources.load(max_age=0)
    manual = seatmap.entries(load_data())
    rows = []
    for seat in sorted(set(merged) | set(manual), key=seatmap._natural):
        m = merged.get(seat, {})
        from_ = m.get('field_sources') or {}
        rows.append({
            'seat': seat,
            'ip': m.get('ip_address') or '',
            'mac': m.get('mac_address') or '',
            'nick': m.get('username') or '',
            'from': {short: from_.get(long) for long, short in seatmap.FIELDS.items() if from_.get(long)},
            'manual': seatmap.public(seat, manual[seat]) if seat in manual else None,
            'sources': m.get('sources') or [],
        })
    return rows


@bp.route('/seat-mapping')
def seat_mapping_page():
    return spa.render('Seat mapping')


@bp.route('/api/seat-map', methods=['GET'])
def list_mapping():
    rows = _merged()
    info = seat_sources.info()
    return jsonify({'seats': rows, 'sources': info['active'], 'errors': info['errors'],
                    'labels': {s['name']: s['label'] for s in info['available']}})


@bp.route('/api/seat-map/<seat>', methods=['PUT'])
def put_seat(seat):
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            entry = seatmap.put(data, seat, body, user=_user())
        except seatmap.MappingError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    seat_sources.invalidate()
    # No top-level name/username: the audit log's target is the seat, never a nick.
    return jsonify({'seat': seat, 'entry': seatmap.public(seat, entry) if entry else None})


@bp.route('/api/seat-map/<seat>', methods=['DELETE'])
def delete_seat(seat):
    with data_lock:
        data = load_data()
        if not seatmap.remove(data, seat):
            return jsonify({'error': 'This seat has no hand entry'}), 404
        save_data(data)
    seat_sources.invalidate()
    return jsonify({'seat': seat, 'entry': None})


@bp.route('/api/seat-map.csv', methods=['GET'])
def export_csv():
    filename = f"floorbit-seat-mapping-{time.strftime('%Y%m%d-%H%M')}.csv"
    return Response(seatmap.to_csv(load_data()).encode('utf-8-sig'), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"',
                             'Cache-Control': 'no-store'})


@bp.route('/api/seat-map/import', methods=['POST'])
def import_csv():
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get('csv'), str):
        return jsonify({'error': 'Send {"csv": "<file contents>"}'}), 400
    try:
        rows, errors = seatmap.parse_csv(body['csv'])
    except seatmap.MappingError as exc:
        return jsonify({'error': str(exc)}), 400
    if errors:
        return jsonify({'error': f'{len(errors)} line(s) have problems; nothing was imported',
                        'problems': errors[:50]}), 400
    replace = bool(body.get('replace'))
    if body.get('dry_run'):
        existing = seatmap.entries(load_data())
        added = sum(1 for s in rows if s not in existing)
        removed = sum(1 for s in existing if s not in rows) if replace else 0
        return jsonify({'dry_run': True, 'added': added, 'updated': len(rows) - added, 'removed': removed})
    with data_lock:
        data = load_data()
        result = seatmap.import_rows(data, rows, replace=replace, user=_user())
        save_data(data)
    seat_sources.invalidate()
    return jsonify(result)
