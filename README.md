# Floorbit

[![CI](https://github.com/bitsandbricks-ch/floorbit/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/bitsandbricks-ch/floorbit/actions/workflows/ci.yml?query=branch%3Amaster)
[![release](https://img.shields.io/github/v/release/bitsandbricks-ch/floorbit?labelColor=1a1a1a)](https://github.com/bitsandbricks-ch/floorbit/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-43a868?labelColor=1a1a1a)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-bitsandbricks-2ee59d?logo=buymeacoffee&logoColor=white)](https://buymeacoffee.com/bitsandbricks)

The event's network on a floor plan. Place switches and seat blocks on a map of the hall, pull the
switches from NetBox, see their live status and ports from LibreNMS, and find which switch port
each seat is plugged into.

<!-- TODO: screenshots of the new frontend (desktop and phone) once the shell rework is merged.
     The CI `screenshots` job takes them; save them as docs/screenshots/*.png and show them here:

![Floor plan](docs/screenshots/floorplan-desktop.png)
-->

## What it does

- **Floor plan:** place, move and rename switches and seat blocks. More than one hall or floor, each
  with its own plan and background image; seat blocks can come from a CSV file. See [docs/halls.md](docs/halls.md).
- **Templates:** save the floor plan as a template with versions, start from one later, or share one
  with another LAN as a file, never with event data in it. See [docs/templates.md](docs/templates.md).
- **Inventory:** every switch, access point and other device, added by hand or fed by NetBox
  (devices with the roles in `NETBOX_DEVICE_ROLE`). What you change by hand is never overwritten by
  a sync. See [docs/inventory.md](docs/inventory.md).
- **LibreNMS:** live status and port counts per switch, and the ARP and MAC tables that resolve a
  seat's IP to its switch and port.
- **Offline mode:** when LibreNMS drops out, pages show the last good data greyed out with its age,
  and Discord gets one "unreachable" message instead of a switch-down flood. See
  [docs/offline.md](docs/offline.md).
- **Demo mode:** `FLOORBIT_DEMO=1` fills Floorbit with a made-up hall, players and traffic, to try it
  without a network. See [docs/demo.md](docs/demo.md).
- **Seat mapping:** each seat's IP, MAC and nick, typed in by hand (or imported as CSV) or fed by
  plugins, check-ins and `seats.json`; what you type wins. See [docs/seat-mapping.md](docs/seat-mapping.md).
- **Seats:** `seats.json` maps seat numbers to IPs and usernames. The heat map colours each seat by
  its port's traffic.
- **Sign-in:** the editor and the settings need an account; the floor plan data stays readable for
  kiosk screens. Username and password, or **Sign in with Discord**: members of your Discord server
  get an account with a role from their server roles, and your own **OpenID Connect** providers
  (Authentik, Keycloak, Entra ID, ...) with groups mapped to roles. See [docs/auth.md](docs/auth.md).
- **Incidents:** a board for problems at seats and switches, worked by your teams, with a QR code on
  every seat so attendees can report "no internet" in one tap. See [docs/incidents.md](docs/incidents.md).
- **Tech dispatch:** send an incident to the nearest free tech; techs see their jobs on their phone
  with the seat on the hall plan. See [docs/dispatch.md](docs/dispatch.md).
- **Service health wall:** DHCP leases, DNS, the LAN cache, game servers and the uplink, green, amber or
  red, on an ops screen or a kiosk, with a Discord message when one goes red. Each check is a plugin.
  See [docs/health.md](docs/health.md).
- **Port actions:** bounce a seat's switch port from the floor plan over SSH with the tech's own login
  (never stored), or flag the seat for a tech. See [docs/ports.md](docs/ports.md).
- **Security detection:** rogue DHCP, ARP spoofing, MAC flapping, loops and storms from security plugins,
  pointing at the seat and port, with one-click port shutdown. See [docs/security.md](docs/security.md).
- **Problems and alerts:** one list of everything wrong right now, mutes for switches someone is
  working on, quiet hours, one Discord message for a big outage, and the ports that need a look
  (flapping, errors rising, half duplex, online without a check-in). See [docs/alerts.md](docs/alerts.md).
- **Stats:** bandwidth now and at its peak (last hour, 24 hours, the event), uplink load per switch,
  seats online and the busiest ports, with a big-screen version. See [docs/stats.md](docs/stats.md).
- **Replay:** play the event back on the floor plan with a time slider: the hall filling up, the
  bandwidth peak and the incidents. See [docs/replay.md](docs/replay.md).
- **Event report:** after the event, a report to read or download as PDF: attendance over time, peak
  bandwidth, switch outages, the top problem ports and the incidents. No nicks or IPs unless an admin
  asks. See [docs/report.md](docs/report.md).
- **Traffic:** what the hall's traffic is made of from NetFlow or IPFIX (gaming, streaming,
  downloads, updates), per area, the services most seats use, and P2P floods or rogue servers.
  Aggregate only, with an optional collector container. See [docs/flows.md](docs/flows.md).
- **Big screens:** `/screen` rotates the floor plan, a traffic heat view and the stats on a timer,
  with a QR code to a "find your seat" page for players' phones. See [docs/kiosk.md](docs/kiosk.md).
- **Attendee view:** `/hall`, a public hall plan with every seat online or offline (seat numbers only,
  off until switched on in Settings). See [docs/kiosk.md](docs/kiosk.md#attendee-view).
- **Electrics:** distribution boards and the circuits they feed (rows, seat blocks, switches), the load
  on each from typed-in or metered readings, and an incident for the Electrics team before a breaker
  trips. A power layer on the floor plan shows what goes dark. See [docs/power.md](docs/power.md).
- **Find a player:** search by nick, seat, IP or MAC, jump to the seat and see the switch port it is
  plugged into, even through the ARP table. See [docs/seat-mapping.md](docs/seat-mapping.md#finding-a-player).
- **Phones and tablets:** tap, drag and pinch on the floor plan, search in a drawer and details in a
  bottom sheet, so a tech on the floor can look up a seat or switch. See [docs/mobile.md](docs/mobile.md).
- **Roles and teams:** Admin, Lead, Tech, Viewer and Kiosk, plus your own roles made from
  permissions, and teams with sub-teams (Infra › Core, Access, Wi-Fi). Nicks and IPs stay hidden from
  viewers and kiosk screens.
- **Themes:** the Floorbit look by default, plus Ops, Kiosk and Classic presets and a custom theme
  with your event's colours, name and logo. Each screen can pick its own with `?theme=`. See
  [docs/themes.md](docs/themes.md).
- **Backup:** download the floor plan and settings as one file and restore it later, without
  tokens or accounts. See [docs/backup.md](docs/backup.md).
- **Audit log:** who changed what and when, and every sign-in, under Settings. See
  [docs/audit.md](docs/audit.md).
- **Plugins and dashboard:** plugins add actions, dashboard tiles, endpoints and hooks, each
  limited to the areas it lists. Floorbit ships an HTTP check. See [docs/plugins.md](docs/plugins.md).
- **Cache:** LibreNMS answers are cached in Redis (5 minutes by default), so a busy hall doesn't hammer
  the API.

NetBox and LibreNMS are optional: leave their URL or token empty and the app runs as a plain floor
plan editor.

## Run it

With Docker Compose (Floorbit on port 8080, plus Redis):

```sh
cp .env.example .env                    # optional: NetBox, LibreNMS, ...
docker compose up -d
docker compose logs floorbit | grep "setup code"
```

Open <http://localhost:8080>, choose **Set up Floorbit** and enter the setup code: you create the
first admin and connect NetBox and LibreNMS (each step can be skipped). The full guide, with NetBox and LibreNMS, a reverse proxy,
backups and updating, is [docs/install.md](docs/install.md). The image is built by CI and pushed to
the GitHub container registry: `ghcr.io/bitsandbricks-ch/floorbit:latest` (from `master`) and
`:<version>` (from a release).

## Configuration

Everything is set through environment variables (`.env` works too). See [`.env.example`](.env.example).

| Variable | Default | What it does |
| --- | --- | --- |
| `NETBOX_URL`, `NETBOX_TOKEN` | empty | NetBox API, read by the built-in NetBox plugin to fill the inventory. |
| `NETBOX_DEVICE_ROLE` | `access-switch` | Device role slugs to show, comma separated. |
| `NETBOX_VERIFY_SSL` | `true` | `false` accepts a self-signed certificate. |
| `LIBRENMS_URL`, `LIBRENMS_TOKEN` | empty | LibreNMS API. Both set turns status, ports and seat resolving on. |
| `LIBRENMS_VERIFY_SSL` | `true` | `false` accepts a self-signed certificate. |
| `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | `localhost`, `6379`, `0`, empty | The cache. Compose points the app at its own `redis` service. |
| `FLOORBIT_DATA_FILE` | `data.json` | Where the floor plan, accounts and settings are kept; the audit log and plugin state go next to it. The image uses `/app/state/data.json`. |
| `FLOORBIT_PORT`, `FLOORBIT_VERSION` | `8080`, `latest` | Compose only: the port on this machine and the image tag ([docs/install.md](docs/install.md)). |
| `CACHE_TTL_ARP`, `CACHE_TTL_MAC` | `300` | Seconds to keep a switch's ARP and MAC tables. |
| `FLOORBIT_THEME` | `floorbit` | Site theme: `floorbit`, `ops`, `kiosk`, `classic` or `custom` ([docs/themes.md](docs/themes.md)). |
| `FLOORBIT_EVENT_NAME` | empty | Event name in the top bar and on the kiosk. |
| `AUDIT_FILE` | next to `data.json` | Where the audit log is kept ([docs/audit.md](docs/audit.md)). |
| `PLUGINS_FILE` | next to `data.json` | Which plugins are on, and their state ([docs/plugins.md](docs/plugins.md)). |
| `SECRET_KEY` | generated | Signs the session cookie. Empty: generated once and kept in `data.json`. |
| `AUTH_ADMIN_USER`, `AUTH_ADMIN_PASSWORD` | empty | Creates the first account when there is none. |
| `AUTH_ENABLED`, `AUTH_PUBLIC_READ`, ... | `true`, `true` | Sign-in switches; all of them are in [docs/auth.md](docs/auth.md). |
| `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_GUILD_ID` | empty | Sign in with Discord; also under Settings > Discord sign-in ([docs/auth.md](docs/auth.md#sign-in-with-discord)). |

The floor plan itself (positions, seat blocks, settings) lives in `data.json`: back it up, or use
Settings > Backup and restore ([docs/backup.md](docs/backup.md)).

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
find static -name '*.js' -exec node --check {} \;
docker build .
```

| Path | What lives there |
| --- | --- |
| `app.py` | Entry point; the app itself is built by `create_app()` in `floorbit/`. |
| `floorbit/` | The Flask app: `blueprints/` (pages and JSON API), `inventory.py` (the device list), `sources/` (asks the monitoring plugin), `builtin_plugins/` (NetBox, LibreNMS, HTTP check), settings, Redis cache. See [docs/architecture.md](docs/architecture.md). |
| `integrations/` | Live updates, switch monitor, Discord alerts, seat sources, check-in. |
| `auth/` | Sign-in: accounts, sessions, the login page and the login providers (password, Discord). |
| `frontend/` | The React app (TypeScript, Mantine). The dashboard and Settings > Plugins are in it so far; the other pages follow. See [frontend/README.md](frontend/README.md). |
| `templates/`, `static/` | The other pages (plain JavaScript and CSS, no build step); the editor is in `static/js/editor/`. |
| `changelog.d/` | One changelog fragment per pull request. |
| `seats.json` | Seat number to IP and username. |
| `tests/` | pytest smoke tests. |
| `scripts/screenshots.py` | Desktop and phone screenshots for pull requests. |
| `docs/` | Design notes and plans. |

### CI

GitHub Actions in [`.github/workflows/`](.github/workflows/), set up like the
[BitsAndBricks repo template](https://github.com/bitsandbricks-ch/repo-template):

| Workflow / job | When | What it does |
| --- | --- | --- |
| `ci.yml` `ruff` | always | Python lint; findings show inline on the pull request. |
| `ci.yml` `javascript` | always | Syntax check of `static/js`. |
| `ci.yml` `frontend` | always | The React app: `npm audit` (production packages), ESLint, TypeScript, Vitest and a production build. |
| `ci.yml` `pytest` | always | Smoke tests. |
| `ci.yml` `screenshots` | pull requests | Runs the app with demo data and screenshots every page, desktop and phone (artifact). |
| `ci.yml` `workflows` | always | actionlint over the workflow files. |
| `ci.yml` `CI passed` | always | Green when every job above is; the one check the `master` ruleset requires. |
| `image.yml` | always | Builds the Docker image; pushes it to GHCR from `master` (`latest`) and `v*` tags (the version). |
| `release.yml` | `v*` tags | Checks the tag against `VERSION` and publishes the GitHub release with its changelog section. |

Branch and tag protection live in [`.github/rulesets/`](.github/rulesets/) (`mason doctor --fix` applies them).

Pull requests follow [CONTRIBUTING.md](CONTRIBUTING.md) and always include screenshots. Coding
agents follow [AGENTS.md](AGENTS.md). Security problems go through a private vulnerability report, see
[SECURITY.md](SECURITY.md).

## Releases

`python scripts/changelog.py collect` merges the `changelog.d/` fragments into `CHANGELOG.md`
(commit that on the release branch), `mason bump floorbit minor` opens the version pull request, `mason release tag floorbit`
pushes the tag, and CI builds the image and publishes the release. See
[CHANGELOG.md](CHANGELOG.md).

## History

Floorbit was called LAL Floor Plan and started on GitLab as
[reykime-private/reykime-lal/lal-floorplan](https://gitlab.com/reykime-private/reykime-lal/lal-floorplan)
(private) and moved here in November 2026. The commit history came along; the merge request
discussions (!1 to !16) and the first issue stay on GitLab.

## License

[AGPL-3.0](LICENSE). If you run a changed version for others over a network, you must offer them
its source.

---

Powered by [BitsAndBricks](https://bitsandbricks.ch).
