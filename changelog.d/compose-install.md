### Added

- Install guide for Docker Compose (`docs/install.md`): one `docker compose up -d`, first account,
  NetBox and LibreNMS, reverse proxy, backups and updating.
- `GET /healthz` for the container healthcheck and load balancers.
- `FLOORBIT_DATA_FILE` sets where `data.json` (and the files next to it) live.

### Changed

- The compose file pulls the published image, keeps all state in one `floorbit_state` volume, and
  answers on port 8080 (`FLOORBIT_PORT`). The service is called `floorbit`. Upgrading from the old
  file: see "From an older compose file" in `docs/install.md`.

### Security

- The image runs gunicorn as an unprivileged user instead of `python app.py` (the Flask development
  server in debug mode) as root.
- Redis is no longer published on port 6379; only Floorbit reaches it.

### Fixed

- A missing `seats.json` no longer shows as a seat source error on a fresh install.
