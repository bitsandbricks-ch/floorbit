"""The seat mapping page and API (floorbit/seatmap.py has the rules).

A seat is mapped by its switch port. The IP and MAC are read off that port; the page can also find
a port from a MAC, which fills the form and can be changed again.

Personal data (nicks, IPs, MACs), so everything here is editors and up, never public, whatever
AUTH_PUBLIC_READ says (auth/roles.py EDITOR_PATHS).

- ``GET /api/seat-map``: the merged mapping, which source gave each field, the hand entries.
- ``PUT /api/seat-map/<seat>``: set a seat's hand entry (``switch``, ``port``, ``ip``, ``mac``,
  ``nick``, ``note``).
- ``POST /api/seat-map/find-port``: ``{"mac"}`` or ``{"ip"}``: the switch port it is seen on now.
- ``POST /api/seat-map/resolve-ports``: give the hand entries that have only an IP or MAC their port
  (``{"dry_run": true}`` only says which).
- ``DELETE /api/seat-map/<seat>``: drop the hand entry; the other sources show again.
- ``GET /api/seat-map.csv``: the hand entries as CSV.
- ``POST /api/seat-map/import``: CSV (``{"csv": "...", "replace": false, "dry_run": true}``),
  every row checked before anything is written.
"""
import time

from flask import Blueprint, Response, current_app, jsonify, request

from integrations import seat_sources

from .. import incidents, seatmap, sources, spa
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
    data = load_data()
    manual = seatmap.entries(data)
    # The same seat set the dashboards count (every hall): rows outside it come from a source only.
    plan = incidents.seat_numbers(data)
    # The seat block each seat is in, for the page's block filter (issue #872).
    from .. import seat_names
    blocks = {seat.upper(): b.get('name') or '' for b in data.get('seat_blocks') or [] for seat in seat_names.seats(b)}
    rows = []
    for seat in sorted(set(merged) | set(manual), key=seatmap._natural):
        m = merged.get(seat, {})
        from_ = m.get('field_sources') or {}
        rows.append({
            'seat': seat,
            'switch': m.get('switch') or '',
            'port': m.get('port') or '',
            'port_origin': 'manual' if from_.get('port') == 'manual' else (m.get('port_origin') or ''),
            'ip': m.get('ip_address') or '',
            'mac': m.get('mac_address') or '',
            'nick': m.get('username') or '',
            'from': {short: from_.get(long) for long, short in seatmap.FIELDS.items() if from_.get(long)},
            'manual': seatmap.public(seat, manual[seat]) if seat in manual else None,
            'sources': m.get('sources') or [],
            'on_plan': seat.upper() in plan,
            'block': blocks.get(seat.upper(), ''),
        })
    return rows


@bp.route('/seat-mapping')
def seat_mapping_page():
    return spa.render('Seat mapping')


@bp.route('/api/seat-map', methods=['GET'])
def list_mapping():
    finder = current_app.extensions.get('floorbit_port_clients')
    if finder is not None and request.args.get('read') == '1':
        finder.request()        # the MACs and IPs on the seat ports, at most every two minutes
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
    errors = seatmap.import_conflicts(load_data(), rows, replace=replace)
    if errors:
        return jsonify({'error': f'{len(errors)} line(s) have problems; nothing was imported',
                        'problems': errors[:50]}), 400
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


def _find(mac='', ip=''):
    """{switch, port, ip, mac} where the monitoring source sees this machine now, or None."""
    monitor = sources.monitoring()
    if not monitor.enabled():
        return None
    if mac and not ip:
        ip = monitor.ip_for_mac(mac) or ''
    if ip and not mac:
        mac = monitor.mac_for_ip(ip) or ''
    found = (monitor.resolve_ip(ip) or {}) if ip else {}
    if not (found.get('device_name') and found.get('port')):
        return None
    return {'switch': found['device_name'], 'port': found['port'], 'ip': ip, 'mac': mac}


@bp.route('/api/seat-map/find-port', methods=['POST'])
def find_port():
    body = request.get_json(silent=True) or {}
    try:
        mac, ip = seatmap.clean_mac(body.get('mac')), seatmap.clean_ip(body.get('ip'))
    except seatmap.MappingError as exc:
        return jsonify({'error': str(exc)}), 400
    if not mac and not ip:
        return jsonify({'error': 'Give a MAC or an IP to look for.'}), 400
    found = _find(mac, ip)
    if not found:
        return jsonify({'error': 'No switch sees this machine right now.'}), 404
    holder = seatmap.holder(seatmap.entries(load_data()), found, str(body.get('seat') or ''))
    return jsonify({**found, 'held_by': holder})


@bp.route('/api/seat-map/resolve-ports', methods=['POST'])
def resolve_ports():
    """Existing hand entries were keyed by IP or MAC: give them the port where that is seen now."""
    body = request.get_json(silent=True) or {}
    todo = {seat: e for seat, e in seatmap.entries(load_data()).items()
            if not e.get('switch') and (e.get('ip_address') or e.get('mac_address'))}
    found, missed = {}, []
    for seat, e in sorted(todo.items(), key=lambda kv: seatmap._natural(kv[0]))[:seatmap.MAX_ROWS]:
        hit = _find(e.get('mac_address') or '', e.get('ip_address') or '')
        if hit:
            found[seat] = {'switch': hit['switch'], 'port': hit['port']}
        else:
            missed.append(seat)
    if body.get('dry_run') or not found:
        return jsonify({'dry_run': bool(body.get('dry_run')), 'found': found, 'missed': missed, 'taken': []})
    taken = []
    with data_lock:
        data = load_data()
        table = seatmap.entries(data)
        for seat, port in found.items():
            entry = table.get(seat)
            if entry is None or entry.get('switch'):
                continue
            other = seatmap.holder(table, port, seat)
            if other:
                taken.append({'seat': seat, 'held_by': other, **port})
                continue
            entry.update(port)
        save_data(data)
    seat_sources.invalidate()
    return jsonify({'dry_run': False, 'found': {s: p for s, p in found.items() if s not in {t['seat'] for t in taken}},
                    'missed': missed, 'taken': taken})
