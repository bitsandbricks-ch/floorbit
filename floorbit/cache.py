"""Redis: the connection and the LibreNMS answer cache.

Redis is optional: without it every lookup goes to LibreNMS and nothing is cached.
"""
import json
import os
import time

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from .runtime import rt

REDIS_HOST     = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT     = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB       = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

redis_client = None


RETRY_EVERY = 15     # seconds between tries while Redis is away
PING_EVERY = 5       # seconds between checks of a working connection
_next_try = 0.0
_checked_at = 0.0


def connect(now=None):
    """Runs before each request: keep the Redis connection, or note that there is none.

    Redis is optional, so a missing one must cost a request nothing: one quick try at most every
    RETRY_EVERY seconds, never a wait or a retry loop inside the request (that made every page take
    half a minute while Redis was down)."""
    global redis_client, _next_try, _checked_at
    now = time.monotonic() if now is None else now
    if redis_client is not None:
        if now - _checked_at < PING_EVERY:
            return
        try:
            redis_client.ping()
            _checked_at = now
            return
        except redis.RedisError as e:
            print(f"Redis went away: {e}. Caching is off until it is back.")
            redis_client, _next_try = None, now + RETRY_EVERY
            return
    if now < _next_try:
        return
    _next_try = now + RETRY_EVERY
    client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=5,
        health_check_interval=30,
        # redis-py retries a refused connection with growing sleeps by default: seconds per request.
        retry=Retry(NoBackoff(), 1),
    )
    try:
        client.ping()
    except redis.RedisError as e:
        print(f"Redis at {REDIS_HOST}:{REDIS_PORT} is not reachable ({e}); caching is off, trying again in "
              f"{RETRY_EVERY} s.")
        return
    redis_client, _checked_at = client, now
    print(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")


def get_redis_client():
    """Get the current Redis client."""
    return redis_client



# ── Redis cache helpers ────────────────────────────────────────────────────────
def get_cached_arp(hostname):
    """Get cached ARP table for a device."""
    client = get_redis_client()
    if not client:
        return None
    try:
        cache_key = f"arp:{hostname}"
        cached = client.get(cache_key)
        if cached:
            return json.loads(cached)
    except (redis.RedisError, ValueError) as e:
        print(f"Redis cache read error (ARP): {e}")
    return None


def set_cached_arp(hostname, arp_data):
    """Cache ARP table for a device."""
    client = get_redis_client()
    if not client:
        return
    try:
        cache_key = f"arp:{hostname}"
        client.setex(cache_key, rt.cache_ttl_arp, json.dumps(arp_data))
    except redis.RedisError as e:
        print(f"Redis cache write error (ARP): {e}")


def get_cached_mac(hostname):
    """Get cached MAC address table for a device."""
    client = get_redis_client()
    if not client:
        return None
    try:
        cache_key = f"mac:{hostname}"
        cached = client.get(cache_key)
        if cached:
            return json.loads(cached)
    except (redis.RedisError, ValueError) as e:
        print(f"Redis cache read error (MAC): {e}")
    return None


def set_cached_mac(hostname, mac_data):
    """Cache MAC address table for a device."""
    client = get_redis_client()
    if not client:
        return
    try:
        cache_key = f"mac:{hostname}"
        client.setex(cache_key, rt.cache_ttl_mac, json.dumps(mac_data))
    except redis.RedisError as e:
        print(f"Redis cache write error (MAC): {e}")


def invalidate_hostname_cache(hostname):
    """Forget a switch's ARP and MAC tables, and every IP last seen on it, so the next lookup asks
    LibreNMS again (after a re-patch, say)."""
    client = get_redis_client()
    if not client:
        return
    try:
        client.delete(f"arp:{hostname}", f"mac:{hostname}")
        name = str(hostname).lower()
        for key in client.scan_iter(match='resolve:*'):
            try:
                seen = json.loads(client.get(key) or 'null') or {}
            except ValueError:
                seen = {}
            if not isinstance(seen, dict) or name in (str(seen.get('hostname') or '').lower(),
                                                      str(seen.get('device_name') or '').lower(),
                                                      str(seen.get('arp_source') or '').lower()):
                client.delete(key)
    except redis.RedisError as e:
        print(f"Redis cache invalidation error: {e}")


def redis_info():
    client = get_redis_client()
    connected = False
    if client:
        try:
            connected = bool(client.ping())
        except redis.RedisError:
            connected = False
    return {'host': REDIS_HOST, 'port': REDIS_PORT, 'db': REDIS_DB, 'connected': connected}
