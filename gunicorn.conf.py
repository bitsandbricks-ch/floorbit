"""Read by gunicorn from its working directory (the Docker image's /app).

The defaults live here, not on the image's command line: gunicorn lets ``GUNICORN_CMD_ARGS`` override
this file but not the command line, so ``GUNICORN_CMD_ARGS=--threads 200`` (docs/install.md) did
nothing while they were there.
"""
import contextlib
import os

MAX_WORKERS = 4         # what docs/sizing.md measured; more mostly adds memory


def cpus():
    """The CPUs this container may use: its cgroup quota, else the CPUs it may run on."""
    count = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else (os.cpu_count() or 1)
    with contextlib.suppress(OSError, ValueError):
        with open('/sys/fs/cgroup/cpu.max') as f:
            quota, period = f.read().split()[:2]
        if quota != 'max':
            count = min(count, max(1, int(quota) // int(period)))
    return max(1, count)


def default_workers():
    # Without the cluster each worker would poll, alert and hold terminals on its own: one worker.
    # With it only the leader polls and the others serve pages (issue #1417), one per CPU.
    if not (os.environ.get('FLOORBIT_CLUSTER') or '').strip():
        return 1
    return min(MAX_WORKERS, cpus())


bind = '0.0.0.0:5000'
workers = default_workers()
worker_class = 'gthread'
# Threads serve the open live-update streams (one per browser tab) and the page requests.
threads = 64
accesslog = '-'


def when_ready(server):
    if server.cfg.workers > 1 and not (os.environ.get('FLOORBIT_CLUSTER') or '').strip():
        # Each worker would run its own watchers and send its own alerts, and a page could ask a
        # worker that doesn't hold its terminal or its agent's link.
        print(f'[cluster] {server.cfg.workers} workers without FLOORBIT_CLUSTER: each one acts on its own '
              '(duplicate alerts, live updates and agent calls only within a worker). Set '
              'FLOORBIT_CLUSTER=valkey and REDIS_HOST, see docs/sizing.md.', flush=True)


def post_fork(server, worker):
    # Each live-update stream holds one of these threads; Floorbit keeps some free for page
    # requests (integrations/events.py, stream_limit).
    os.environ['FLOORBIT_SERVER_THREADS'] = str(worker.cfg.threads)


def post_worker_init(worker):
    # The background loops start with a worker's first request (integrations/__init__.py). With
    # several workers only the leader polls (issue #1417), and it may get no request for a while:
    # one /healthz in process starts each worker's loops now.
    if worker.cfg.workers > 1 and hasattr(worker.wsgi, 'test_client'):
        with contextlib.suppress(Exception):
            worker.wsgi.test_client().get('/healthz')
