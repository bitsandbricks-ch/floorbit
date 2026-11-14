"""Live network data: switch status, IP to switch port, the seat mapping and the seat heatmap.

While the monitoring source is down, answers come from its last good data, marked ``stale`` with
``as_of`` and ``offline_since`` (floorbit/sources, docs/offline.md)."""
from flask import Blueprint, jsonify, request

from integrations import seat_sources

from .. import inventory, sources
from ..seat_traffic import collect_seat_heatmap
from ..store import load_data

bp = Blueprint('network', __name__)


@bp.route('/api/switches/<switch_id>/status', methods=['GET'])
def get_switch_status(switch_id):
    if not sources.monitoring().enabled():
        return jsonify({
            'id':      switch_id,
            'status':  'unknown',
            'message': 'LibreNMS is not configured',
        })

    device = inventory.find(load_data(), switch_id)
    hostname = device['name'] if device else switch_id

    details = sources.monitoring().device_details(hostname)
    return jsonify({'id': switch_id, **details})


@bp.route('/api/monitoring/health', methods=['GET'])
def monitoring_health():
    """Is the monitoring source answering? When not, since when (pages show cached data meanwhile)."""
    source = sources.monitoring()
    return jsonify({'enabled': source.enabled(), 'name': source.name, 'label': source.label,
                    **sources.health()})


@bp.route('/api/resolve/<ip_address>', methods=['GET'])
def resolve_ip(ip_address):
    """Resolve an IP address to its switch and port using LibreNMS ARP and MAC tables."""
    if not sources.monitoring().enabled():
        return jsonify({
            'ip': ip_address,
            'error': 'LibreNMS is not configured',
        }), 400

    # Optional: specify a device to search for ARP entries
    search_device = request.args.get('device')

    result = sources.monitoring().resolve_ip(ip_address, search_device)
    if result:
        return jsonify(result)
    else:
        return jsonify({
            'ip': ip_address,
            'error': 'Could not resolve IP address',
        }), 404


@bp.route('/api/seats/info', methods=['GET'])
def get_seats_info():
    """Seat → user / IP mapping, merged from the configured seat sources."""
    seats = seat_sources.load()
    return jsonify({'seats': seats, 'errors': seat_sources.info()['errors']})


@bp.route('/api/seats/occupancy', methods=['GET'])
def get_seats_occupancy():
    """Which seats are taken, and nothing else: no nicks, IPs or MACs. For viewers and kiosks;
    the full mapping (/api/seats/info) needs seats.view."""
    seats = seat_sources.load()
    taken = sorted(s for s, v in seats.items() if any((v or {}).get(k) for k in ('username', 'ip_address')))
    return jsonify({'taken': taken})


@bp.route('/api/seats/resolve', methods=['POST'])
def resolve_seats():
    """Resolve all seat IP addresses to their switch and port mappings."""
    if not sources.monitoring().enabled():
        return jsonify({
            'error': 'LibreNMS is not configured',
        }), 400

    seats = seat_sources.load()
    if not seats:
        return jsonify({'error': 'No seat mapping available', 'sources': seat_sources.info()}), 400

    results = {}

    for seat_number, seat_info in seats.items():
        ip_address = seat_info.get('ip_address')
        if not ip_address:
            continue

        # Try to resolve the IP
        result = sources.monitoring().resolve_ip(ip_address)
        if result:
            results[seat_number] = {
                'username': seat_info.get('username'),
                'ip_address': ip_address,
                'resolved': True,
                **result,
            }
        else:
            results[seat_number] = {
                'username': seat_info.get('username'),
                'ip_address': ip_address,
                'resolved': False,
                'error': 'Could not resolve',
            }

    return jsonify({'seats': results})


@bp.route('/api/seats/heatmap', methods=['GET'])
def get_seats_heatmap():
    """Get seat heat map data based on port usage statistics."""
    if not sources.monitoring().enabled():
        return jsonify({
            'error': 'LibreNMS is not configured',
        }), 400

    seats = seat_sources.load()
    if not seats:
        return jsonify({'error': 'No seat mapping available', 'sources': seat_sources.info()}), 400

    # Seats are looked up in parallel; see seat_traffic.py.
    return jsonify({'seats': collect_seat_heatmap(seats, sources.monitoring().resolve_ip)})
