"""Redis: the connection and the LibreNMS answer cache.

Redis is optional: without it every lookup goes to LibreNMS and nothing is cached.
"""
import json
import os
import time

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from .env import number
from .runtime import rt

REDIS_HOST     = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT     = number('REDIS_PORT', 6379, minimum=1)
REDIS_DB       = number('REDIS_DB', 0, minimum=0)
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

redis_client = None


class Prefixed:
    """A Redis client whose keys start with the hosted tenant's name, so tenants can share one
    Redis (docs/tenancy.md). Only the commands Floorbit uses on it; add one here before using it."""

    def __init__(self, client, prefix):
        self.client, self.prefix = client, prefix

    def _k(self, key):
        return self.prefix + key

    def ping(self):
        return self.client.ping()

    def get(self, key):
        return self.client.get(self._k(key))

    def set(self, key, value, **kw):
        return self.client.set(self._k(key), value, **kw)

    def setex(self, key, ttl, value):
        return self.client.setex(self._k(key), ttl, value)

    def delete(self, *keys):
        return self.client.delete(*(self._k(k) for k in keys))

    def exists(self, *keys):
        return self.client.exists(*(self._k(k) for k in keys))

    def expire(self, key, ttl):
        return self.client.expire(self._k(key), ttl)

    def dbsize(self):
        # Only this tenant's keys: the others aren't its business.
        return sum(1 for _ in self.client.scan_iter(match=self._k('*')))

    def scan_iter(self, match='*', **kw):
        cut = len(self.prefix)
        for key in self.client.scan_iter(match=self._k(match), **kw):
            yield key[cut:]


def redis_prefix():
    # Every tenant's keys and channels start with its name, the default tenant's too, so tenants
    # sharing one Redis never see each other's. (Redis only holds a cache that fills again.)
    from .store import current_tenant
    return f'{current_tenant()}:'


def _scoped(client):
    return Prefixed(client, redis_prefix())


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
    redis_client, _checked_at = _scoped(client), now
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
