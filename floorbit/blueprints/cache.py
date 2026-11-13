"""Inspect and clear the Redis cache of LibreNMS answers."""
import redis
from flask import Blueprint, jsonify, request

from ..cache import get_redis_client, invalidate_hostname_cache
from ..runtime import rt

bp = Blueprint('cache', __name__)


@bp.route('/api/cache/invalid', methods=['POST'])
def invalidate_cache():
    """Invalidate Redis cache entries for specific hostnames."""
    client = get_redis_client()
    if not client:
        return jsonify({'error': 'Redis is not configured'}), 503

    body = request.get_json(force=True) or {}
    hostnames = body.get('hostnames', [])

    if not hostnames:
        # Invalidate all cache if no hostnames specified
        try:
            # Delete all ARP and MAC cache keys
            for key in client.scan_iter(match='arp:*'):
                client.delete(key)
            for key in client.scan_iter(match='mac:*'):
                client.delete(key)
            return jsonify({'success': True, 'message': 'All cache entries invalidated'})
        except redis.RedisError as e:
            return jsonify({'error': f'Failed to clear cache: {e!s}'}), 500

    # Invalidate cache for specific hostnames
    invalidated = []
    for hostname in hostnames:
        try:
            invalidate_hostname_cache(hostname)
            invalidated.append(hostname)
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
