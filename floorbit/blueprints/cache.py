"""Inspect and clear the Redis cache of LibreNMS answers."""
import redis
from flask import Blueprint, jsonify, request

from ..cache import get_redis_client, invalidate_hostname_cache
from ..runtime import rt

bp = Blueprint('cache', __name__)


KINDS = ('arp', 'mac', 'resolve')   # resolve: where an IP was last seen, so a cleared cache finds it anew
MAX_HOSTNAMES = 500


@bp.route('/api/cache/invalid', methods=['POST'])
def invalidate_cache():
    """Forget the cached LibreNMS answers: for some switches (``hostnames``), or all of them."""
    client = get_redis_client()
    if not client:
        return jsonify({'error': 'Redis is not configured'}), 503

    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    hostnames = body.get('hostnames') or []
    if not isinstance(hostnames, list) or len(hostnames) > MAX_HOSTNAMES \
            or not all(isinstance(h, str) and h.strip() for h in hostnames):
        return jsonify({'error': 'hostnames is a list of switch names'}), 400

    if not hostnames:
        try:
            for kind in KINDS:
                keys = list(client.scan_iter(match=f'{kind}:*'))
                if keys:
                    client.delete(*keys)
            return jsonify({'success': True, 'message': 'All cache entries invalidated'})
        except redis.RedisError as e:
            return jsonify({'error': f'Failed to clear cache: {e!s}'}), 500

    invalidated = []
    for hostname in hostnames:
        try:
            invalidate_hostname_cache(hostname.strip())
            invalidated.append(hostname.strip())
        except redis.RedisError as e:
            print(f"Failed to invalidate cache for {hostname}: {e}")
    return jsonify({
        'success': True,
        'message': f'Cache invalidated for {len(invalidated)} hostnames',
        'invalidated': invalidated
    })


@bp.route('/api/cache/stats', methods=['GET'])
def get_cache_stats():
    """Get Redis cache statistics."""
    client = get_redis_client()
    if not client:
        return jsonify({'error': 'Redis is not configured'}), 503

    try:
        # Count ARP and MAC cache keys
        arp_count = len(list(client.scan_iter(match='arp:*')))
        mac_count = len(list(client.scan_iter(match='mac:*')))
        total_keys = client.dbsize()

        return jsonify({
            'redis_connected': True,
            'total_keys': total_keys,
            'arp_cache_entries': arp_count,
            'mac_cache_entries': mac_count,
            'cache_ttl_arp': rt.cache_ttl_arp,
            'cache_ttl_mac': rt.cache_ttl_mac,
        })
    except redis.RedisError as e:
        return jsonify({'error': f'Failed to get cache stats: {e!s}'}), 500
