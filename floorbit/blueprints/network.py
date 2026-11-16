"""Live network data: switch status, IP to switch port, the seat mapping and the seat heatmap.

While the monitoring source is down, answers come from its last good data, marked ``stale`` with
``as_of`` and ``offline_since`` (floorbit/sources, docs/offline.md)."""
from flask import Blueprint, jsonify, request

from integrations import seat_sources

from .. import inventory, seat_search, sources
from ..seat_traffic import collect_seat_heatmap
from ..seat_traffic import resolve_seats as resolve_each_seat
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

    details = dict(sources.monitoring().device_details(hostname) or {})
    from flask import current_app

    from auth import current_user  # late: auth imports floorbit while it loads
    guard = current_app.extensions.get('auth')
    if guard and guard.enabled and current_user() is None:
        details.pop('ip', None)    # a signed-out kiosk only draws the status; management IPs need an account
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


@bp.route('/api/seats/find', methods=['GET'])
def find_seat():
    """A player by nick, seat, IP or MAC: their seat, block and switch port (floorbit/seat_search.py)."""
    return jsonify(seat_search.find(request.args.get('q', '')[:100]))


@bp.route('/api/seats/occupancy', methods=['GET'])
def get_seats_occupancy():
    """Which seats are taken, and nothing else: no nicks, IPs or MACs. For viewers and kiosks;
    the full mapping (/api/seats/info) needs seats.view."""
    seats = seat_sources.load()
    taken = sorted(s for s, v in seats.items() if any((v or {}).get(k) for k in ('username', 'ip_address')))
    return jsonify({'taken': taken})


@bp.route('/api/seats/resolve', methods=['POST'])
def resolve_seats():
    """Every seat with an IP: its switch and port, or why it could not be found."""
    if not sources.monitoring().enabled():
        return jsonify({
            'error': 'LibreNMS is not configured',
        }), 400

    seats = seat_sources.load()
    if not seats:
        return jsonify({'error': 'No seat mapping available', 'sources': seat_sources.info()}), 400

    # In parallel, like the heatmap; one failing lookup marks only its seat (issue #198).
    results = resolve_each_seat(seats, sources.monitoring().resolve_ip)
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
    monitoring = sources.monitoring()
    return jsonify({'seats': collect_seat_heatmap(seats, monitoring.resolve_ip, port_stats=monitoring.port_stats)})
