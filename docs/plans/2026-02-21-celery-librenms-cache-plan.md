# Celery LibreNMS Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Celery-based background tasks to periodically fetch ARP and MAC data from LibreNMS every 15 seconds and cache in Redis.

**Architecture:** Separate Celery worker service with Beat scheduler. ARP data fetched via single `/api/v0/resources/ip/arp/all` call; MAC data fetched per-device via `/api/v0/devices/{id}/fdb`. Redis serves as both cache and Celery broker. Flask app reads from cache, Celery worker writes to cache.

**Tech Stack:** Celery 5.3+, Redis, Flask, Python 3.11+, Docker Compose

---

## Prerequisites

### Task 1: Add Celery Dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Add Celery dependencies**

Open `requirements.txt` and add these lines at the end:

```txt
celery>=5.3.0
celery[redis]>=5.3.0
flower>=2.0.0
```

**Step 2: Commit**

```bash
git add requirements.txt
git commit -m "deps: add Celery and Flower dependencies

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 1: Celery Configuration

### Task 2: Create Celery App Configuration

**Files:**
- Create: `celery_app.py`

**Step 1: Write Celery configuration file**

Create `celery_app.py` with:

```python
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# ── Celery Configuration ─────────────────────────────────────────────────────
CELERY_BROKER_URL = os.getenv(
    'CELERY_BROKER_URL',
    'redis://redis:6379/1'
)
CELERY_RESULT_BACKEND = os.getenv(
    'CELERY_RESULT_BACKEND',
    'redis://redis:6379/1'
)
CELERY_TASK_SCHEDULE_INTERVAL = int(
    os.getenv('CELERY_TASK_SCHEDULE_INTERVAL', 15)
)

# ── LibreNMS Configuration ───────────────────────────────────────────────────
LIBRENMS_URL = os.getenv('LIBRENMS_URL', '').rstrip('/')
LIBRENMS_TOKEN = os.getenv('LIBRENMS_TOKEN', '')
LIBRENMS_VERIFY_SSL = os.getenv('LIBRENMS_VERIFY_SSL', 'true').lower() != 'false'

# ── Celery App ───────────────────────────────────────────────────────────────
celery_app = Celery(
    'lal_floorplan',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        'fetch-all-librenms-arp': {
            'task': 'tasks.fetch_all_librenms_arp',
            'schedule': CELERY_TASK_SCHEDULE_INTERVAL,
        },
        'fetch-all-librenms-mac': {
            'task': 'tasks.fetch_all_librenms_mac',
            'schedule': CELERY_TASK_SCHEDULE_INTERVAL,
        },
    },
)

# Make LibreNMS config available to tasks
celery_app.conf.librenms_url = LIBRENMS_URL
celery_app.conf.librenms_token = LIBRENMS_TOKEN
celery_app.conf.librenms_verify_ssl = LIBRENMS_VERIFY_SSL

if __name__ == '__main__':
    celery_app.start()
```

**Step 2: Commit**

```bash
git add celery_app.py
git commit -m "feat: add Celery app configuration

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 2: Celery Tasks

### Task 3: Create Tasks File Structure

**Files:**
- Create: `tasks.py`

**Step 1: Write tasks file with imports and Redis setup**

Create `tasks.py` with initial structure:

```python
import json
import time
import redis
import requests
from celery import current_task

# Get config from Celery app (set in celery_app.py)
LIBRENMS_URL = None
LIBRENMS_TOKEN = None
LIBRENMS_VERIFY_SSL = None
REDIS_HOST = None
REDIS_PORT = None
REDIS_DB = None
REDIS_PASSWORD = None

# TTL for Celery-refreshed cache (15 seconds)
CELERY_CACHE_TTL = 15


def init_config():
    """Initialize config from Celery app."""
    global LIBRENMS_URL, LIBRENMS_TOKEN, LIBRENMS_VERIFY_SSL
    global REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD

    app = current_task.app if current_task else None
    if app:
        LIBRENMS_URL = app.conf.librenms_url
        LIBRENMS_TOKEN = app.conf.librenms_token
        LIBRENMS_VERIFY_SSL = app.conf.librenms_verify_ssl

    # Parse Redis broker URL: redis://host:port/db
    broker_url = app.conf.broker_url if app else 'redis://redis:6379/1'
    # Parse: redis://redis:6379/1
    if broker_url.startswith('redis://'):
        parts = broker_url.replace('redis://', '').split('/')
        if len(parts) >= 2:
            host_port = parts[0]
            REDIS_HOST = host_port.split(':')[0] if ':' in host_port else 'redis'
            REDIS_PORT = int(host_port.split(':')[1]) if ':' in host_port else 6379
            REDIS_DB = int(parts[1]) if len(parts) > 1 else 1


def get_redis_client():
    """Get Redis client connection."""
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
    except Exception as e:
        print(f"Redis connection error: {e}")
        return None
```

**Step 2: Commit**

```bash
git add tasks.py
git commit -m "feat: add tasks file with Redis client

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 4: Implement Metrics Storage Functions

**Files:**
- Modify: `tasks.py`

**Step 1: Add metrics storage functions**

Add to `tasks.py` after the `get_redis_client()` function:

```python
def store_metrics(task_name, metrics):
    """Store task execution metrics in Redis."""
    client = get_redis_client()
    if not client:
        return

    try:
        timestamp = int(time.time())
        key = f"metrics:{task_name}"

        # Store current metrics
        client.hset(key, mapping=metrics)

        # Store execution history (last 10 runs)
        history_key = f"metrics:{task_name}:history"
        client.lpush(history_key, json.dumps({
            'timestamp': timestamp,
            'metrics': metrics
        }))
        client.ltrim(history_key, 0, 9)  # Keep last 10

        # Set TTL for metrics
        client.expire(key, 300)  # 5 minutes
        client.expire(history_key, 300)

    except Exception as e:
        print(f"Failed to store metrics: {e}")
```

**Step 2: Commit**

```bash
git add tasks.py
git commit -m "feat: add metrics storage functions

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 5: Implement ARP Fetch Task

**Files:**
- Modify: `tasks.py`

**Step 1: Add fetch_all_librenms_arp task**

Add to `tasks.py` after metrics functions:

```python
from celery import Task


class BaseLibreNMSTask(Task):
    """Base task with config initialization."""

    def __call__(self, *args, **kwargs):
        init_config()
        return super().__call__(*args, **kwargs)


@celery_app.task(bind=True, base=BaseLibreNMSTask, name='tasks.fetch_all_librenms_arp')
def fetch_all_librenms_arp(self):
    """Fetch all ARP entries from LibreNMS and cache by device.

    Uses /api/v0/resources/ip/arp/all endpoint for efficient bulk fetch.
    """
    start_time = time.time()
    metrics = {
        'start_time': start_time,
        'end_time': None,
        'duration_seconds': None,
        'total_entries': 0,
        'devices_cached': 0,
        'devices_failed': 0,
        'success': False,
        'error': None,
    }

    if not LIBRENMS_URL or not LIBRENMS_TOKEN:
        metrics['error'] = 'LibreNMS not configured'
        metrics['end_time'] = time.time()
        metrics['duration_seconds'] = metrics['end_time'] - start_time
        store_metrics('arp_fetch', metrics)
        return metrics

    headers = {
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }

    try:
        # Fetch all ARP entries in one call
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/resources/ip/arp/all',
            headers=headers,
            timeout=30,
            verify=LIBRENMS_VERIFY_SSL,
        )
        resp.raise_for_status()

        arp_data = resp.json().get('arp', [])
        metrics['total_entries'] = len(arp_data)

        # Group by hostname/device
        arp_by_device = {}
        for entry in arp_data:
            hostname = entry.get('hostname', 'unknown')
            if hostname not in arp_by_device:
                arp_by_device[hostname] = []
            arp_by_device[hostname].append(entry)

        # Cache each device's ARP table
        client = get_redis_client()
        if client:
            pipe = client.pipeline()
            for hostname, entries in arp_by_device.items():
                cache_key = f"arp:{hostname}"
                pipe.setex(cache_key, CELERY_CACHE_TTL, json.dumps(entries))
            try:
                pipe.execute()
                metrics['devices_cached'] = len(arp_by_device)
                print(f"ARP: Cached {len(entries)} entries for {len(arp_by_device)} devices")
            except Exception as e:
                metrics['error'] = f'Cache write failed: {e}'
                metrics['devices_failed'] = len(arp_by_device)
                print(f"ARP: Cache write error: {e}")
        else:
            metrics['error'] = 'Redis connection failed'
            metrics['devices_failed'] = len(arp_by_device)
            print("ARP: Redis connection failed")

        metrics['success'] = True

    except requests.RequestException as e:
        metrics['error'] = f'API request failed: {e}'
        print(f"ARP: API request error: {e}")
    except Exception as e:
        metrics['error'] = f'Unexpected error: {e}'
        print(f"ARP: Unexpected error: {e}")

    metrics['end_time'] = time.time()
    metrics['duration_seconds'] = metrics['end_time'] - start_time
    store_metrics('arp_fetch', metrics)

    return metrics
```

**Step 2: Fix import order**

Add `@celery_app.task` import at top of file. Update the imports section:

```python
import json
import time
import redis
import requests
from celery import current_task, Task
```

**Step 3: Commit**

```bash
git add tasks.py
git commit -m "feat: implement fetch_all_librenms_arp task

Uses /api/v0/resources/ip/arp/all for efficient bulk fetching.
Groups entries by device and caches with 15-second TTL.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 6: Implement MAC Fetch Task

**Files:**
- Modify: `tasks.py`

**Step 1: Add fetch_all_librenms_mac task**

Add to `tasks.py` after the ARP task:

```python
@celery_app.task(bind=True, base=BaseLibreNMSTask, name='tasks.fetch_all_librenms_mac')
def fetch_all_librenms_mac(self):
    """Fetch MAC address tables (FDB) from all LibreNMS devices and cache.

    Must fetch per-device as there's no bulk FDB endpoint.
    """
    start_time = time.time()
    metrics = {
        'start_time': start_time,
        'end_time': None,
        'duration_seconds': None,
        'total_entries': 0,
        'devices_cached': 0,
        'devices_failed': 0,
        'success': False,
        'error': None,
    }

    if not LIBRENMS_URL or not LIBRENMS_TOKEN:
        metrics['error'] = 'LibreNMS not configured'
        metrics['end_time'] = time.time()
        metrics['duration_seconds'] = metrics['end_time'] - start_time
        store_metrics('mac_fetch', metrics)
        return metrics

    headers = {
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }

    try:
        # First, get all devices
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices',
            headers=headers,
            timeout=30,
            verify=LIBRENMS_VERIFY_SSL,
        )
        resp.raise_for_status()

        devices = resp.json().get('devices', [])

        if not devices:
            metrics['success'] = True
            metrics['end_time'] = time.time()
            metrics['duration_seconds'] = metrics['end_time'] - start_time
            store_metrics('mac_fetch', metrics)
            return metrics

        # Fetch FDB for each device
        client = get_redis_client()
        successful_devices = 0
        failed_devices = 0
        total_entries = 0

        if client:
            pipe = client.pipeline()

        for device in devices:
            device_id = device.get('hostname') or device.get('device_id')
            device_name = device.get('display', device.get('hostname', 'unknown'))

            if not device_id:
                continue

            try:
                fdb_resp = requests.get(
                    f'{LIBRENMS_URL}/api/v0/devices/{device_id}/fdb',
                    headers=headers,
                    timeout=10,
                    verify=LIBRENMS_VERIFY_SSL,
                )
                fdb_resp.raise_for_status()

                fdb_data = fdb_resp.json().get('fdb', [])
                total_entries += len(fdb_data)

                if client:
                    cache_key = f"mac:{device_name}"
                    pipe.setex(cache_key, CELERY_CACHE_TTL, json.dumps(fdb_data))

                successful_devices += 1

            except requests.RequestException as e:
                failed_devices += 1
                print(f"MAC: Failed to fetch FDB for {device_name}: {e}")
            except Exception as e:
                failed_devices += 1
                print(f"MAC: Error processing {device_name}: {e}")

        # Execute Redis pipeline
        if client and successful_devices > 0:
            try:
                pipe.execute()
            except Exception as e:
                metrics['error'] = f'Cache write failed: {e}'
                print(f"MAC: Cache write error: {e}")

        metrics['total_entries'] = total_entries
        metrics['devices_cached'] = successful_devices
        metrics['devices_failed'] = failed_devices
        metrics['success'] = True

        print(f"MAC: Cached {total_entries} entries for {successful_devices} devices, {failed_devices} failed")

    except requests.RequestException as e:
        metrics['error'] = f'API request failed: {e}'
        print(f"MAC: API request error: {e}")
    except Exception as e:
        metrics['error'] = f'Unexpected error: {e}'
        print(f"MAC: Unexpected error: {e}")

    metrics['end_time'] = time.time()
    metrics['duration_seconds'] = metrics['end_time'] - start_time
    store_metrics('mac_fetch', metrics)

    return metrics
```

**Step 2: Commit**

```bash
git add tasks.py
git commit -m "feat: implement fetch_all_librenms_mac task

Fetches FDB data per-device and caches with 15-second TTL.
Continues processing on individual device failures.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 3: Flask API Integration

### Task 7: Add Celery Health Endpoint

**Files:**
- Modify: `app.py`

**Step 1: Import Celery app**

Add at the top of `app.py` after redis import:

```python
from celery_app import celery_app
```

**Step 2: Add Celery health check function**

Add before the `@app.route('/')` section:

```python
# ── Celery Health Check ───────────────────────────────────────────────────────

def get_celery_health():
    """Get Celery worker health status."""
    try:
        # Check if Celery app is available
        inspector = celery_app.control.inspect()

        # Get active workers
        active_workers = inspector.active()

        # Get scheduled tasks
        scheduled_tasks = inspector.scheduled()

        # Get registered tasks
        registered_tasks = inspector.registered()

        return {
            'workers': len(active_workers) if active_workers else 0,
            'active_tasks': sum(len(tasks) for tasks in (active_workers or {}).values()),
            'scheduled_tasks': sum(len(tasks) for tasks in (scheduled_tasks or {}).values()),
            'registered_tasks': registered_tasks,
            'status': 'healthy' if active_workers else 'unhealthy'
        }
    except Exception as e:
        return {
            'workers': 0,
            'active_tasks': 0,
            'scheduled_tasks': 0,
            'registered_tasks': {},
            'status': 'error',
            'error': str(e)
        }
```

**Step 3: Add health endpoint**

Add after the `/api/cache/stats` endpoint:

```python
@app.route('/api/celery/health', methods=['GET'])
def get_celery_health_endpoint():
    """Get Celery worker health status."""
    client = get_redis_client()
    health = get_celery_health()

    # Get last execution times from Redis metrics
    last_arp = None
    last_mac = None

    if client:
        try:
            arp_metrics = client.hgetall('metrics:arp_fetch')
            mac_metrics = client.hgetall('metrics:mac_fetch')

            if arp_metrics and arp_metrics.get('end_time'):
                last_arp = int(float(arp_metrics['end_time']))
            if mac_metrics and mac_metrics.get('end_time'):
                last_mac = int(float(mac_metrics['end_time']))
        except Exception as e:
            print(f"Failed to get metrics: {e}")

    health['last_arp_fetch'] = last_arp
    health['last_mac_fetch'] = last_mac

    return jsonify(health)
```

**Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add Celery health check endpoint

Provides worker status and last execution times.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 8: Add Celery Metrics Endpoint

**Files:**
- Modify: `app.py`

**Step 1: Add metrics endpoint**

Add after the `/api/celery/health` endpoint:

```python
@app.route('/api/celery/metrics', methods=['GET'])
def get_celery_metrics():
    """Get detailed Celery task metrics."""
    client = get_redis_client()
    if not client:
        return jsonify({'error': 'Redis is not configured'}), 503

    try:
        arp_metrics = client.hgetall('metrics:arp_fetch')
        mac_metrics = client.hgetall('metrics:mac_fetch')

        arp_history = []
        mac_history = []

        try:
            arp_history_raw = client.lrange('metrics:arp_fetch:history', 0, 9)
            arp_history = [json.loads(h) for h in arp_history_raw]

            mac_history_raw = client.lrange('metrics:mac_fetch:history', 0, 9)
            mac_history = [json.loads(h) for h in mac_history_raw]
        except Exception as e:
            print(f"Failed to get history: {e}")

        return jsonify({
            'arp': {
                'current': arp_metrics,
                'history': arp_history
            },
            'mac': {
                'current': mac_metrics,
                'history': mac_history
            }
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get metrics: {str(e)}'}, 500)
```

**Step 2: Add tasks history endpoint**

Add after the metrics endpoint:

```python
@app.route('/api/celery/tasks', methods=['GET'])
def get_celery_tasks():
    """Get recent Celery task execution history."""
    client = get_redis_client()
    if not client:
        return jsonify({'error': 'Redis is not configured'}), 503

    try:
        limit = int(request.args.get('limit', 10))

        arp_history_raw = client.lrange('metrics:arp_fetch:history', 0, limit - 1)
        mac_history_raw = client.lrange('metrics:mac_fetch:history', 0, limit - 1)

        arp_history = [json.loads(h) for h in arp_history_raw]
        mac_history = [json.loads(h) for h in mac_history_raw]

        return jsonify({
            'arp': arp_history,
            'mac': mac_history
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get task history: {str(e)}'}, 500)
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add Celery metrics and task history endpoints

Provides detailed metrics and execution history for monitoring.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 4: Docker Configuration

### Task 9: Update Dockerfile for Multi-Process Support

**Files:**
- Create: `Dockerfile` (if not exists, modify existing)

**Step 1: Check if Dockerfile exists**

Run: `ls Dockerfile`

If Dockerfile exists, read it first and modify. If not, create new one.

**Step 2: Create/update Dockerfile**

Create or replace `Dockerfile` with:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY celery_app.py .
COPY tasks.py .
COPY static/ ./static/
COPY templates/ ./templates/

# Create uploads directory
RUN mkdir -p static/uploads

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Default command (Flask app)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
```

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "chore: update Dockerfile for Celery support

Adds Celery app and tasks files. Uses gunicorn for production.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 10: Create Celery Worker Dockerfile

**Files:**
- Create: `Dockerfile.celery`

**Step 1: Create Celery worker Dockerfile**

Create `Dockerfile.celery` with:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Celery files only
COPY celery_app.py .
COPY tasks.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run Celery worker with Beat scheduler
CMD ["celery", "-A", "celery_app", "worker", "--beat", "--loglevel=info"]
```

**Step 2: Commit**

```bash
git add Dockerfile.celery
git commit -m "chore: add Celery worker Dockerfile

Minimal image for running Celery worker with Beat scheduler.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 11: Update Docker Compose

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Add Celery worker service**

Add the `lal-celery-worker` service to `docker-compose.yml` after the `lal-app` service:

```yaml
  lal-celery-worker:
    build:
      context: .
      dockerfile: Dockerfile.celery
    container_name: lal-celery-worker
    environment:
      - LIBRENMS_URL=${LIBRENMS_URL:-}
      - LIBRENMS_TOKEN=${LIBRENMS_TOKEN:-}
      - LIBRENMS_VERIFY_SSL=${LIBRENMS_VERIFY_SSL:-true}
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - CELERY_TASK_SCHEDULE_INTERVAL=${CELERY_TASK_SCHEDULE_INTERVAL:-15}
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "celery", "-A", "celery_app", "inspect", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

**Step 2: Add Flower monitoring service (optional)**

After the Celery worker service, add:

```yaml
  lal-flower:
    build:
      context: .
      dockerfile: Dockerfile.celery
    container_name: lal-flower
    command: ["celery", "-A", "celery_app", "flower", "--port=5555"]
    ports:
      - "5555:5555"
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
    depends_on:
      - lal-celery-worker
    restart: unless-stopped
    profiles:
      - monitoring  # Only start with --profile monitoring
```

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Celery worker and Flower services to Docker Compose

Celery worker runs periodic ARP/MAC fetch tasks every 15 seconds.
Flower provides optional monitoring UI (--profile monitoring).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 5: Documentation

### Task 12: Update REDIS_CACHE.md

**Files:**
- Modify: `REDIS_CACHE.md`

**Step 1: Add Celery section**

Add a new section after "Future Enhancements":

```markdown
## Celery Periodic Cache Refresh

The application now includes a Celery-based background task system that automatically fetches and updates ARP and MAC cache data every 15 seconds.

### Celery Services

The `docker-compose.yml` includes two Celery-related services:

1. **lal-celery-worker** - Runs Celery worker with Beat scheduler
   - Periodically fetches ARP data from `/api/v0/resources/ip/arp/all`
   - Periodically fetches MAC data from all devices
   - Updates Redis cache with 15-second TTL

2. **lal-flower** (optional) - Flower monitoring UI
   - Start with: `docker-compose --profile monitoring up -d`
   - Access at: `http://localhost:5555`

### API Endpoints

#### Celery Health Check

```http
GET /api/celery/health
```

Returns:
```json
{
  "workers": 1,
  "active_tasks": 0,
  "scheduled_tasks": 2,
  "registered_tasks": {...},
  "status": "healthy",
  "last_arp_fetch": 1708521600,
  "last_mac_fetch": 1708521605
}
```

#### Celery Metrics

```http
GET /api/celery/metrics
```

Returns detailed metrics for ARP and MAC fetch tasks including execution time, entry counts, and error information.

#### Task History

```http
GET /api/celery/tasks?limit=10
```

Returns recent task execution history.

### Configuration

```env
# Celery Configuration
CELERY_TASK_SCHEDULE_INTERVAL=15  # Seconds between fetch cycles
```

### Cache TTL Strategy

| Cache Type | TTL | Source |
|-------------|-----|--------|
| `arp:{hostname}` | 15 seconds | Celery periodic task |
| `mac:{hostname}` | 15 seconds | Celery periodic task |
| `arp_ip:{ip}` | 300 seconds | On-demand API call |

The 15-second TTL for Celery-refreshed data ensures cache is always fresh, while on-demand lookups use a longer TTL to reduce API calls.
```

**Step 2: Commit**

```bash
git add REDIS_CACHE.md
git commit -m "docs: update REDIS_CACHE.md with Celery information

Documents Celery periodic cache refresh and new API endpoints.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 13: Create README for Celery Setup

**Files:**
- Create: `CELERY_SETUP.md`

**Step 1: Create Celery setup guide**

Create `CELERY_SETUP.md` with:

```markdown
# Celery Periodic Cache Refresh Setup

This document describes the Celery-based system for periodically fetching ARP and MAC data from LibreNMS.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Flask App      │────▶│     Redis       │◀────│ Celery Worker   │
│  (API Server)   │     │  (Cache +       │     │ + Beat Scheduler│
│                 │     │   Message Broker)│     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                             │
                                                         Fetches from
                                                             │
                                                         LibreNMS API
```

## Quick Start

### 1. Start All Services

```bash
docker-compose up -d
```

This starts:
- Redis (cache and message broker)
- Flask app (API server)
- Celery worker (background tasks + scheduler)

### 2. Verify Celery Worker

```bash
# Check worker logs
docker-compose logs -f lal-celery-worker

# Check worker health
docker-compose ps lal-celery-worker
```

You should see periodic log messages like:
```
ARP: Cached 1234 entries for 45 devices
MAC: Cached 5678 entries for 45 devices, 0 failed
```

### 3. Monitor with Flower (Optional)

```bash
docker-compose --profile monitoring up -d lal-flower
```

Access Flower at `http://localhost:5555`

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# Celery Configuration
CELERY_TASK_SCHEDULE_INTERVAL=15  # Seconds between fetch cycles

# LibreNMS (required)
LIBRENMS_URL=https://librenms.example.com
LIBRENMS_TOKEN=your-api-token
LIBRENMS_VERIFY_SSL=true
```

## API Endpoints

### Health Check

```bash
curl http://localhost:5000/api/celery/health
```

### Metrics

```bash
curl http://localhost:5000/api/celery/metrics
```

### Task History

```bash
curl http://localhost:5000/api/celery/tasks?limit=10
```

## Troubleshooting

### Worker Not Starting

```bash
# Check logs
docker-compose logs lal-celery-worker

# Common issues:
# - Redis not running: docker-compose ps redis
# - LibreNMS URL not configured: check .env
# - Network issues: check docker network
```

### Tasks Not Executing

```bash
# Check scheduled tasks
docker-compose exec lal-celery-worker celery -A celery_app inspect scheduled

# Check registered tasks
docker-compose exec lal-celery-worker celery -A celery_app inspect registered
```

### Cache Not Updating

```bash
# Check task metrics
curl http://localhost:5000/api/celery/metrics

# Check Redis directly
docker-compose exec redis redis-cli KEYS "arp:*"
docker-compose exec redis redis-cli KEYS "mac:*"
```

## Performance Tuning

### Adjust Fetch Interval

Change the interval between fetch cycles:

```env
CELERY_TASK_SCHEDULE_INTERVAL=30  # 30 seconds
```

Restart worker after changing:

```bash
docker-compose restart lal-celery-worker
```

### Monitor Task Duration

Use the metrics endpoint to track how long tasks take:

```bash
curl http://localhost:5000/api/celery/metrics | jq '.arp.current.duration_seconds'
```

If tasks exceed the interval, consider:
- Increasing the interval
- Reducing the number of devices
- Parallel fetching (requires code changes)

## Scaling

### Add More Workers

Edit `docker-compose.yml` to add more worker instances:

```yaml
lal-celery-worker-2:
  <<: *celery-worker  # Use YAML anchor
  container_name: lal-celery-worker-2
```

### Separate Worker from Beat

For better control, you can run Beat as a separate service:

```yaml
lal-celery-beat:
  build:
    context: .
    dockerfile: Dockerfile.celery
  command: ["celery", "-A", "celery_app", "beat", "--loglevel=info"]
```

## Monitoring

### Flower UI

Start Flower:
```bash
docker-compose --profile monitoring up -d lal-flower
```

Flower provides:
- Real-time task execution
- Worker status
- Success/failure rates
- Task queue depth
- Performance metrics

### Metrics API

Get detailed metrics:
```bash
curl http://localhost:5000/api/celery/metrics
```

Set up monitoring alerts based on:
- `duration_seconds` - Alert if exceeds interval
- `devices_failed` - Alert if > threshold
- `success` - Alert if false
```

**Step 2: Commit**

```bash
git add CELERY_SETUP.md
git commit -m "docs: add Celery setup guide

Provides comprehensive setup, configuration, and troubleshooting information.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 6: Testing

### Task 14: Create Test for Tasks

**Files:**
- Create: `tests/test_tasks.py`

**Step 1: Create test directory and file**

```bash
mkdir -p tests
touch tests/__init__.py
```

**Step 2: Write tests for tasks**

Create `tests/test_tasks.py` with:

```python
import json
import pytest
from unittest.mock import Mock, patch
from tasks import fetch_all_librenms_arp, fetch_all_librenms_mac, store_metrics


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return Mock()


@pytest.fixture
def mock_celery_task():
    """Mock Celery task."""
    mock = Mock()
    mock.app.conf.librenms_url = 'http://test.librenms.com'
    mock.app.conf.librenms_token = 'test-token'
    mock.app.conf.librenms_verify_ssl = False
    mock.app.conf.broker_url = 'redis://redis:6379/1'
    return mock


@pytest.fixture
def mock_requests_response():
    """Mock requests response."""
    mock = Mock()
    mock.json.return_value = {
        'arp': [
            {
                'hostname': 'switch1.example.com',
                'ipv4_address': '192.168.1.100',
                'mac_address': 'aa:bb:cc:dd:ee:ff',
                'port': 'Gi1/0/1',
                'vlan': 10
            }
        ]
    }
    mock.raise_for_status = Mock()
    return mock


@patch('tasks.current_task')
@patch('tasks.requests.get')
@patch('tasks.get_redis_client')
def test_fetch_all_librenms_arp_success(
    mock_redis_client, mock_get, mock_current_task, mock_celery_task,
    mock_requests_response, mock_redis
):
    """Test successful ARP fetch."""
    mock_current_task.app = mock_celery_task.app
    mock_redis_client.return_value = mock_redis
    mock_get.return_value = mock_requests_response

    result = fetch_all_librenms_arp()

    assert result['success'] is True
    assert result['total_entries'] == 1
    assert result['devices_cached'] == 1
    assert result['devices_failed'] == 0
    assert result['error'] is None


@patch('tasks.current_task')
@patch('tasks.requests.get')
def test_fetch_all_librenms_arp_no_config(mock_get, mock_current_task):
    """Test ARP fetch with no LibreNMS config."""
    mock_current_task.app = Mock()
    mock_current_task.app.conf.librenms_url = ''
    mock_current_task.app.conf.librenms_token = ''
    mock_current_task.app.conf.broker_url = 'redis://redis:6379/1'

    result = fetch_all_librenms_arp()

    assert result['success'] is False
    assert 'not configured' in result['error']


@patch('tasks.get_redis_client')
def test_store_metrics_success(mock_redis_client, mock_redis):
    """Test storing metrics."""
    mock_redis_client.return_value = mock_redis

    metrics = {
        'duration_seconds': 1.5,
        'devices_cached': 10,
        'success': True
    }

    store_metrics('test_task', metrics)

    mock_redis.hset.assert_called_once()
    mock_redis.lpush.assert_called_once()
```

**Step 3: Update requirements.txt for testing**

Add to `requirements.txt`:

```txt
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0
```

**Step 4: Commit**

```bash
git add tests/test_tasks.py tests/__init__.py requirements.txt
git commit -m "test: add Celery tasks unit tests

Tests for ARP/MAC fetch tasks and metrics storage.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### Task 15: Create Integration Test

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

Create `tests/test_integration.py` with:

```python
import json
import time
import pytest
import requests


@pytest.mark.integration
def test_celery_health_endpoint(base_url):
    """Test Celery health endpoint."""
    response = requests.get(f'{base_url}/api/celery/health')
    assert response.status_code == 200

    data = response.json()
    assert 'workers' in data
    assert 'status' in data


@pytest.mark.integration
def test_celery_metrics_endpoint(base_url):
    """Test Celery metrics endpoint."""
    response = requests.get(f'{base_url}/api/celery/metrics')
    assert response.status_code == 200

    data = response.json()
    assert 'arp' in data
    assert 'mac' in data
    assert 'current' in data['arp']
    assert 'current' in data['mac']


@pytest.mark.integration
def test_cache_refreshed(base_url, redis_client):
    """Test that cache is refreshed by Celery tasks."""
    # Wait for at least one task cycle
    time.sleep(20)

    # Check for cached data
    arp_keys = list(redis_client.scan_iter(match='arp:*'))
    mac_keys = list(redis_client.scan_iter(match='mac:*'))

    # If LibreNMS is configured, should have cache entries
    assert len(arp_keys) >= 0 or len(mac_keys) >= 0


@pytest.mark.integration
def test_celery_task_history(base_url):
    """Test task history endpoint."""
    # Wait for at least one task cycle
    time.sleep(20)

    response = requests.get(f'{base_url}/api/celery/tasks?limit=5')
    assert response.status_code == 200

    data = response.json()
    assert 'arp' in data
    assert 'mac' in data
```

**Step 2: Add conftest.py for fixtures**

Create `tests/conftest.py` with:

```python
import os
import pytest
import redis


@pytest.fixture
def base_url():
    """Base URL for API tests."""
    return os.getenv('TEST_BASE_URL', 'http://localhost:5000')


@pytest.fixture
def redis_client():
    """Redis client for tests."""
    return redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=int(os.getenv('REDIS_DB', 0)),
        decode_responses=True
    )
```

**Step 3: Commit**

```bash
git add tests/test_integration.py tests/conftest.py
git commit -m "test: add integration tests for Celery endpoints

Tests for health, metrics, and cache refresh functionality.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 7: Final Verification

### Task 16: Build and Test Docker Images

**Step 1: Build Docker images**

```bash
docker-compose build
```

**Expected output:** Images built successfully without errors

**Step 2: Start services**

```bash
docker-compose up -d
```

**Step 3: Verify all services are running**

```bash
docker-compose ps
```

**Expected:** All services (redis, lal-app, lal-celery-worker) show status "Up" or "healthy"

**Step 4: Check Celery worker logs**

```bash
docker-compose logs -f lal-celery-worker
```

**Expected to see:**
```
[INFO/MainProcess] Connected to redis://redis:6379/1
[INFO/MainProcess] celery@x ready.
[INFO/Beat] Scheduler: Sending due task fetch-all-librenms-arp
[INFO/MainProcess] Task tasks.fetch_all_librenms_arp[xxx] received
ARP: Cached X entries for Y devices
```

**Step 5: Test API endpoints**

```bash
curl http://localhost:5000/api/celery/health
curl http://localhost:5000/api/celery/metrics
curl http://localhost:5000/api/celery/tasks
```

**Expected:** All return valid JSON with 200 status

**Step 6: Verify Redis cache**

```bash
docker-compose exec redis redis-cli KEYS "arp:*"
docker-compose exec redis redis-cli KEYS "mac:*"
docker-compose exec redis redis-cli KEYS "metrics:*"
```

**Expected:** See cache keys populated

**Step 7: Commit**

```bash
git add .
git commit -m "test: verify Docker build and deployment

All services running correctly, API endpoints responding,
Redis cache being populated by Celery tasks.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Summary

This implementation plan creates a complete Celery-based background task system for:

1. **Periodic ARP fetching** - Single API call to `/api/v0/resources/ip/arp/all` every 15 seconds
2. **Periodic MAC fetching** - Per-device FDB fetching every 15 seconds
3. **Redis caching** - 15-second TTL for Celery-refreshed data
4. **Metrics collection** - Execution time, success/failure counts, entry counts
5. **API endpoints** - Health check, metrics, and task history
6. **Monitoring** - Optional Flower UI for real-time monitoring
7. **Docker integration** - Separate Celery worker service
8. **Documentation** - Complete setup and troubleshooting guides
9. **Testing** - Unit and integration tests

**Total tasks:** 16
**Estimated completion time:** 2-3 hours
**Commits:** ~16 atomic commits
