# The React app (frontend/), built into static/app/
FROM node:24-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py VERSION ./
COPY floorbit/ ./floorbit/
COPY auth/ ./auth/
# COPY data.json .
COPY static/ ./static/
COPY --from=frontend /src/static/app/ ./static/app/
COPY templates/ ./templates/
COPY integrations/ ./integrations/

# Everything Floorbit writes (data.json, audit log, plugin state, check-ins) goes to /app/state.
# Owned by an unprivileged user, so a new named volume starts out writable (docs/install.md).
RUN useradd --system --uid 10001 --create-home --home-dir /home/floorbit --shell /usr/sbin/nologin floorbit \
    && mkdir -p /app/state && chown floorbit:floorbit /app/state
VOLUME /app/state

ENV FLASK_APP=app.py \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLOORBIT_DATA_FILE=/app/state/data.json \
    CHECKIN_FILE=/app/state/checkins.json \
    SEAT_SOURCE_JSON_PATH=/app/state/seats.json

USER floorbit
EXPOSE 5000
# The optional flow collector (python -m floorbit.flows, docs/flows.md).
EXPOSE 2055/udp
# The syslog receiver, when SYSLOG_ENABLED is on (docs/syslog.md). Not 514, so no root is needed.
EXPOSE 5514/udp 5514/tcp

# One worker: the status monitor, watchers and live updates live in the process. Threads serve the
# open live-update streams (one per browser tab); raise them with GUNICORN_CMD_ARGS="--threads 200".
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--worker-class", "gthread", "--threads", "64", \
     "--access-logfile", "-", "app:app"]
