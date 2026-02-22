# Redis Caching for LibreNMS ARP and MAC Entries

## Overview

This application now uses Redis to cache LibreNMS ARP and MAC address table entries, reducing API calls and improving response times for seat IP resolution.

## Architecture

- **Redis Server**: Stores cached ARP and MAC table data with configurable TTL
- **Cache Keys**:
  - `arp:{hostname}` - Cached ARP table entries for a device
  - `mac:{hostname}` - Cached MAC address table (FDB) entries for a device
- **Default TTL**: 300 seconds (5 minutes) for both ARP and MAC caches

## Configuration

Add the following environment variables to your `.env` file:

```env
# ── Redis Cache ────────────────────────────────────────────────────────────────
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
# Cache TTL in seconds (default: 5 minutes)
CACHE_TTL_ARP=300
CACHE_TTL_MAC=300
```

## Docker Setup

The `docker-compose.yml` file includes a Redis service:

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: lal-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

  lal-app:
    # ... other config
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
      # ... other env vars
```

To start the application with Redis:

```bash
docker-compose up -d
```

## How Caching Works

1. **First Request**: When ARP or MAC data is requested for a device:
   - Check Redis cache
   - If not found, fetch from LibreNMS API
   - Store in Redis with TTL
   - Return data to client

2. **Subsequent Requests**:
   - Return cached data from Redis
   - No LibreNMS API call made

3. **Cache Expiration**:
   - After TTL expires, next request fetches fresh data from LibreNMS
   - New data is cached with refreshed TTL

## Cache Management API

### Get Cache Statistics

```http
GET /api/cache/stats
```

Returns:
```json
{
  "redis_connected": true,
  "total_keys": 42,
  "arp_cache_entries": 15,
  "mac_cache_entries": 27,
  "cache_ttl_arp": 300,
  "cache_ttl_mac": 300
}
```

### Invalidate Cache

```http
POST /api/cache/invalid
Content-Type: application/json

{
  "hostnames": ["switch1", "switch2"]
}
```

To invalidate all cache entries:
```http
POST /api/cache/invalid
Content-Type: application/json

{}
```

Returns:
```json
{
  "success": true,
  "message": "Cache invalidated for 2 hostnames",
  "invalidated": ["switch1", "switch2"]
}
```

## Performance Benefits

- **Reduced API calls**: ARP and MAC tables are cached for multiple requests
- **Faster response times**: Cache reads are ~10-100x faster than API calls
- **Lower LibreNMS load**: Reduces load on LibreNMS server
- **Graceful degradation**: Application works even if Redis is unavailable

## Monitoring Cache

Check cache hit/miss logs in application logs:

```
ARP cache hit for switch1.example.com
MAC cache miss for switch2.example.com - fetched and cached
```

## Troubleshooting

### Redis Connection Failed

If you see:
```
Warning: Could not connect to Redis: [Errno 111] Connection refused. Caching disabled.
```

- Ensure Redis container is running: `docker ps | grep redis`
- Check Redis service health: `docker-compose logs redis`
- Verify network connectivity between app and Redis containers

### Cache Not Working

1. Check Redis connection status via `/api/cache/stats`
2. Verify environment variables are set correctly
3. Check application logs for Redis-related errors

### Clearing All Cache

```bash
# Via API
curl -X POST http://localhost:5000/api/cache/invalid -H "Content-Type: application/json" -d '{}'

# Via Redis CLI
docker exec -it lal-redis redis-cli FLUSHDB
```

## Local Development Without Redis

If you don't want to use Redis locally, the application will gracefully degrade:

- Set `REDIS_HOST` to a non-existent host
- Or simply don't start the Redis service
- Application will work but always fetch from LibreNMS API

## Security Considerations

- **Redis Authentication**: Set `REDIS_PASSWORD` in production
- **Network Isolation**: Keep Redis on internal Docker network
- **Data Persistence**: Redis volume `redis_data` persists cache across restarts
- **Access Control**: Redis is not exposed externally in default configuration

## Cache Key Naming Convention

```
arp:{hostname}    → JSON array of ARP entries
mac:{hostname}    → JSON array of MAC address table entries
```

Example: `arp:sw-core-01` stores the ARP table for device `sw-core-01`

## Future Enhancements

Potential improvements:
- Cache warming on startup
- Adaptive TTL based on device activity
- Cache invalidation based on LibreNMS webhooks
- Prometheus metrics for cache hit/miss ratios
