"""Read by gunicorn from its working directory (the Docker image's /app).

The defaults live here, not on the image's command line: gunicorn lets ``GUNICORN_CMD_ARGS`` override
this file but not the command line, so ``GUNICORN_CMD_ARGS=--threads 200`` (docs/install.md) did
nothing while they were there.
"""
import os

bind = '0.0.0.0:5000'
# One worker: the status monitor, watchers, terminal sessions and live updates live in the process.
# More workers need what several pods need, see docs/sizing.md.
workers = 1
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
