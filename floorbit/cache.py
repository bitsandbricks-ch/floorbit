"""Redis: the connection and the LibreNMS answer cache.

Redis is optional: without it every lookup goes to LibreNMS and nothing is cached.
"""
import json
import os
import time

import redis

from .runtime import rt

REDIS_HOST     = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT     = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB       = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

redis_client = None


def connect():
    """Establish Redis connection before each request with retry logic."""
    global redis_client

    # If Redis client already exists and is connected, reuse it
    if redis_client:
        try:
            redis_client.ping()
            return
        except redis.RedisError:
            redis_client = None

    # Try to establish new connection with retries
    for attempt in range(5):  # Try up to 5 times
        try:
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Test connection
            redis_client.ping()
            print(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT} (attempt {attempt + 1})")
            return
        except redis.RedisError as e:
            if attempt < 4:  # Don't wait on the last attempt
                print(f"Redis connection attempt {attempt + 1} failed: {e}. Retrying in 2 seconds...")
                time.sleep(2)
            else:
                print(f"Warning: Could not connect to Redis after 5 attempts: {e}. Caching disabled for this request.")
                redis_client = None


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
    """Invalidate all cache entries for a specific hostname."""
    client = get_redis_client()
    if not client:
        return
    try:
        client.delete(f"arp:{hostname}")
        client.delete(f"mac:{hostname}")
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
