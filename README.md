# LAL Floor Plan

[![pipeline](https://gitlab.com/reykime-private/reykime-lal/lal-floorplan/badges/master/pipeline.svg)](https://gitlab.com/reykime-private/reykime-lal/lal-floorplan/-/pipelines?ref=master)
[![release](https://gitlab.com/reykime-private/reykime-lal/lal-floorplan/-/badges/release.svg)](https://gitlab.com/reykime-private/reykime-lal/lal-floorplan/-/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-43a868?labelColor=1a1a1a)](LICENSE)

The event's network on a floor plan. Place switches and seat blocks on a map of the hall, pull the
switches from NetBox, see their live status and ports from LibreNMS, and find which switch port
each seat is plugged into.

<!-- TODO: screenshots of the new frontend (desktop and phone) once the shell rework is merged.
     The pipeline's `screenshots` job takes them; save them as docs/screenshots/*.png and show them here:

![Floor plan](docs/screenshots/floorplan-desktop.png)
-->

## What it does

- **Floor plan:** place, move and rename switches and seat blocks.
- **NetBox:** the switch list comes from NetBox (devices with the roles in `NETBOX_DEVICE_ROLE`);
  you only place them. Manual switches work with or without NetBox.
- **LibreNMS:** live status and port counts per switch, and the ARP and MAC tables that resolve a
  seat's IP to its switch and port.
- **Seats:** `seats.json` maps seat numbers to IPs and usernames. The heat map colours each seat by
  its port's traffic.
- **Cache:** LibreNMS answers are cached in Redis (5 minutes by default), so a busy hall doesn't hammer
  the API.

NetBox and LibreNMS are optional: leave their URL or token empty and the app runs as a plain floor
plan editor.

## Run it

With Docker Compose (the app on port 5002, plus Redis):

```sh
cp .env.example .env        # fill in NetBox and LibreNMS, or leave them empty
touch data.json             # the floor plan is saved here
docker compose up -d
```

Open <http://localhost:5002>. The image is also built by CI and pushed to this project's container
registry: `registry.gitlab.com/reykime-private/reykime-lal/lal-floorplan:latest` (from `master`) and
`:<version>` (from a release).

## Configuration

Everything is set through environment variables (`.env` works too). See [`.env.example`](.env.example).

| Variable | Default | What it does |
| --- | --- | --- |
| `NETBOX_URL`, `NETBOX_TOKEN` | empty | NetBox API. Both set turns the NetBox switch list on. |
| `NETBOX_DEVICE_ROLE` | `access-switch` | Device role slugs to show, comma separated. |
| `NETBOX_VERIFY_SSL` | `true` | `false` accepts a self-signed certificate. |
| `LIBRENMS_URL`, `LIBRENMS_TOKEN` | empty | LibreNMS API. Both set turns status, ports and seat resolving on. |
| `LIBRENMS_VERIFY_SSL` | `true` | `false` accepts a self-signed certificate. |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | `localhost`, `6379`, `0`, empty | The cache. Compose points the app at its own `redis` service. |
| `CACHE_TTL_ARP`, `CACHE_TTL_MAC` | `300` | Seconds to keep a switch's ARP and MAC tables. |

The floor plan itself (positions, seat blocks, settings) lives in `data.json`: back it up.

## Develop

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
docker run -d -p 6379:6379 redis:7-alpine     # or set REDIS_HOST to one you have
python app.py                                  # http://127.0.0.1:5000, reloads on change
```

Before you push, run what the pipeline runs:

```sh
ruff check .
pytest -q                                      # NetBox, LibreNMS and Redis are faked
for f in static/js/*.js; do node --check "$f"; done
docker build .
```

| Path | What lives there |
| --- | --- |
| `app.py` | The Flask app: pages, JSON API, NetBox and LibreNMS clients, Redis cache. |
| `templates/`, `static/` | The pages and the browser app (plain JavaScript and CSS, no build step). |
| `seats.json` | Seat number to IP and username. |
| `tests/` | pytest smoke tests. |
| `scripts/screenshots.py` | Desktop and phone screenshots for merge requests. |
| `docs/` | Design notes and plans. |

### Pipeline

| Job | When | What it does |
| --- | --- | --- |
| `ruff` | always | Python lint; findings show inline in the merge request. |
| `javascript` | always | Syntax check of `static/js`. |
| `pytest` | always | Smoke tests; results show in the merge request. |
| `screenshots` | merge requests | Runs the app with demo data and screenshots every page, desktop and phone. |
| `docker-image` | always | Builds the Docker image; pushes it from `master` and `v*` tags. |
| `release` | `v*` tags | Checks the tag against `VERSION` and publishes the release with its changelog section. |

Merge requests follow [CONTRIBUTING.md](CONTRIBUTING.md) and always include screenshots. Coding
agents follow [AGENTS.md](AGENTS.md). Security problems go through a confidential issue, see
[SECURITY.md](SECURITY.md).

## Releases

`mason bump lal-floorplan minor` opens the version merge request, `mason release tag lal-floorplan`
pushes the tag, and the pipeline builds the image and publishes the release. See
[CHANGELOG.md](CHANGELOG.md).

## License

[AGPL-3.0](LICENSE). If you run a changed version for others over a network, you must offer them
its source.

---

Powered by [BitsAndBricks](https://bitsandbricks.ch).
