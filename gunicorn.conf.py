"""Read by gunicorn from its working directory (the Docker image's /app). Settings stay on the
command line; this only tells Floorbit what it runs on."""
import os


def post_fork(server, worker):
    # Each live-update stream holds one of these threads; Floorbit keeps some free for page
    # requests (integrations/events.py, stream_limit).
    os.environ['FLOORBIT_SERVER_THREADS'] = str(worker.cfg.threads)
