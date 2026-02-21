# Celery-Based LibreNMS Data Fetcher Design

**Date:** 2026-02-21
**Status:** Approved
**Approach:** Celery Beat with Separate Worker Service

## Overview

Implement a Celery-based background task system to periodically fetch ARP tables and MAC address data from LibreNMS every 15 seconds, cache the results in Redis, and provide comprehensive metrics on task performance.

## Requirements

- Fetch ARP tables from ALL LibreNMS devices every 15 seconds
- Fetch MAC address tables from ALL LibreNMS devices every 15 seconds
- Cache results in Redis with 15-second TTL
- Handle device failures gracefully (continue processing other devices)
- Provide full metrics: fetch times, success rates, cache hits/misses, error counts

## Architecture

### Component 1: Celery Configuration (`celery_app.py`)

Separate Celery app instance (independent from Flask) with:

- Redis as both message broker and result backend
- Beat scheduler for periodic task execution
- Configuration for 15-second task intervals
- Settings for task retries (max 3), timeouts, and serialization

### Component 2: Celery Tasks (`tasks.py`)

**Task 1: `fetch_all_librenms_arp()`**
- Uses `/api/v0/resources/ip/arp/all` endpoint (single API call for all devices)
- Parses response containing all ARP entries from all devices
- Groups entries by hostname/device
- Caches each device's ARP table as `arp:{hostname}` with 15-second TTL
- Logs metrics: start time, end time, total entries, devices cached, failures

**Task 2: `fetch_all_librenms_mac()`**
- Fetches all devices list from LibreNMS
- Iterates through each device to fetch FDB using `/api/v0/devices/{device_id}/fdb`
- Caches each device's MAC table as `mac:{hostname}` with 15-second TTL
- Logs metrics: start time, end time, total entries, devices cached, failures

### Component 3: Metrics Collection

Metrics tracked and stored in Redis:
- Task execution time per task type (ARP/MAC)
- Success/failure counts per task cycle
- ARP entry count, MAC entry count
- Cache write success/failure tracking
- Error categorization (network errors, API errors, timeout errors)
- Last successful execution timestamp

### Component 4: Docker Services (`docker-compose.yml`)

New service: `lal-celery-worker`
- Runs Celery worker with Beat scheduler
- Uses same Dockerfile but different entrypoint
- Depends on Redis service
- Environment variables for Celery configuration

### Component 5: API Endpoints

**`GET /api/celery/health`**
- Worker status (running/stopped)
- Last task execution time for ARP and MAC
- Uptime information

**`GET /api/celery/metrics`**
- Detailed metrics per task type:
  - Average fetch time
  - Total entries cached
  - Success/failure counts
  - Error breakdown by type
  - Cache write statistics

**`GET /api/celery/tasks`**
- Recent task execution history (last 10 runs)

## Data Flow

```
Every 15 seconds:
┌─────────────────┐
│  Celery Beat    │
│  Scheduler      │
└────────┬────────┘
         │ triggers
         ▼
┌─────────────────────────────────────────────┐
│ ARP Task:                                  │
│ GET /api/v0/resources/ip/arp/all           │
│ ↓                                          │
│ Parse all ARP entries                       │
│ ↓                                          │
│ Group by hostname/device                    │
│ ↓                                          │
│ Cache as arp:{hostname} in Redis (15s TTL) │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ MAC Task:                                  │
│ GET /api/v0/devices (all)                  │
│ ↓                                          │
│ For each device:                            │
│   GET /api/v0/devices/{id}/fdb              │
│   ↓                                        │
│   Cache as mac:{hostname} in Redis (15s TTL)│
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Redis           │
│ - arp:{hostname}│ (15s TTL - Celery refreshed)
│ - mac:{hostname}│ (15s TTL - Celery refreshed)
│ - arp_ip:{ip}   │ (300s TTL - On-demand cached)
│ - metrics:*     │ (300s TTL)
└─────────────────┘

API requests read from Redis cache
```

## LibreNMS API Usage

### ARP Fetching (Optimized)

**Endpoint:** `GET /api/v0/resources/ip/arp/all`

- Single API call gets ALL ARP entries from ALL devices
- Response format:
  ```json
  {
    "arp": [
      {
        "hostname": "switch1.example.com",
        "ipv4_address": "192.168.1.100",
        "mac_address": "aa:bb:cc:dd:ee:ff",
        "port": "Gi1/0/1",
        "vlan": 10
      },
      ...
    ]
  }
  ```
- Much more efficient than fetching per-device

### MAC Fetching

**Endpoint 1:** `GET /api/v0/devices`
- Get list of all devices

**Endpoint 2:** `GET /api/v0/devices/{device_id}/fdb` (per device)
- No equivalent "all FDB" endpoint available
- Must iterate through devices

## Error Handling

### Device-level Failures

- Log error with device ID, error type, and timestamp
- Continue processing remaining devices
- Record in metrics for API reporting

### Task-level Failures

- Automatic retry with exponential backoff (max 3 retries)
- Log to application logs
- Alert via metrics endpoint if consecutive failures

### Redis Connection Failures

- Graceful degradation (task continues without caching)
- Log warnings
- Track in metrics

## Configuration

### New Environment Variables

```env
# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/1
CELERY_TASK_SCHEDULE_INTERVAL=15
CELERY_TASK_MAX_RETRIES=3
CELERY_TASK_RETRY_DELAY=5
CELERY_METS_TTL=300

# LibreNMS Configuration (existing)
LIBRENMS_URL=https://librenms.example.com
LIBRENMS_TOKEN=your-token-here
LIBRENMS_VERIFY_SSL=true
```

### New Dependencies

```
celery>=5.3.0
celery[redis]>=5.3.0
flower>=2.0.0
```

## File Structure

```
lal-floorplan/
├── app.py                 # Flask app (existing)
├── celery_app.py          # NEW: Celery app configuration
├── tasks.py               # NEW: Celery task definitions
├── requirements.txt       # UPDATED: Add Celery dependencies
├── docker-compose.yml     # UPDATED: Add celery worker service
├── Dockerfile             # UPDATED: Support multiple entrypoints
└── docs/plans/
    └── 2026-02-21-celery-librenms-cache-design.md  # This file
```

## Performance Considerations

- **ARP:** Single API call - very efficient (~100-500ms)
- **MAC:** Per-device calls - consider parallel fetching with Celery `group()`
- **Rate limiting:** Respect LibreNMS API rate limits
- **Memory usage:** Stream large responses; don't load all device data in memory
- **Redis pipeline:** Use Redis pipelining for bulk cache writes
- **TTL optimization:** Set 15-second TTL for Celery-refreshed cache (vs 300s for on-demand)

## Cache Key Strategy

| Key Pattern | Purpose | TTL | Source |
|-------------|---------|-----|--------|
| `arp:{hostname}` | Device ARP table | 15s | Celery task |
| `mac:{hostname}` | Device MAC/FDB table | 15s | Celery task |
| `arp_ip:{ip_address}` | IP-based ARP lookup | 300s | On-demand API call |

## Testing Strategy

1. **Unit tests:** Task functions with mocked LibreNMS API
2. **Integration tests:** With local LibreNMS instance
3. **Performance tests:** With 10+ devices to verify 15-second cycle completes
4. **Error simulation tests:** Network failures, API errors, timeout errors

## Monitoring

### Celery Flower (Optional)

Flower web UI for real-time monitoring:
- Task execution history
- Success/failure rates
- Worker status
- Task queue depth

Access at `http://localhost:5555` when running

### Metrics API

Use `/api/celery/metrics` endpoint to:
- Monitor task health
- Detect performance degradation
- Alert on consecutive failures
- Track cache effectiveness

## Future Enhancements

Potential improvements:
- Cache warming on startup
- Adaptive interval based on device activity
- Webhook-based cache invalidation from LibreNMS
- Prometheus metrics export
- Parallel MAC fetching with Celery chords

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LibreNMS API rate limits | Cache staleness | Monitor response times, implement backoff |
| High device count | Task exceeds 15s window | Parallel MAC fetching, monitor cycle time |
| Redis connection loss | No caching | Graceful degradation, alert on connection loss |
| Worker crashes | Missed fetch cycles | Auto-restart with docker-compose, monitor health |

## Implementation Phases

1. **Phase 1:** Core Celery setup (config, tasks, worker)
2. **Phase 2:** Metrics collection and API endpoints
3. **Phase 3:** Monitoring (Flower) and alerting
4. **Phase 4:** Optimization (parallel fetching, pipelining)
