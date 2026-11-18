# Install with Docker Compose

On Kubernetes or k3s, see [kubernetes.md](kubernetes.md) instead.

Floorbit, its local agent and Valkey (the cache) in three containers, on any machine with Docker. It works
without NetBox or LibreNMS: you place switches by hand and connect those later.

Floorbit itself never talks to the event network: the switches, LibreNMS, NetBox, game servers and
the rest are reached through the [local agent](agent.md), the same way as with a hosted Floorbit.
Here the agent runs next to it, and Floorbit enrols it by itself at start: it writes the agent's key
into the `agent_key` volume, which only the two containers share, and lists it as "Local agent"
under **Settings > Local agents**. Run this machine where it can reach the event network, or run
only the agent there ([agent.md](agent.md)).

You need Docker with Compose 2.24 or newer (`docker compose version`).

## 1. Start it

```sh
mkdir floorbit && cd floorbit
curl -fsSLO https://raw.githubusercontent.com/bitsandbricks-ch/floorbit/master/docker-compose.yml
curl -fsSL -o .env https://raw.githubusercontent.com/bitsandbricks-ch/floorbit/master/.env.example
docker compose up -d
```

<!-- TODO(Mike): the raw URLs and the image pull need the repository and its GHCR package to be public. -->
While the repository is private, clone it and start it with
[Building the image yourself](#building-the-image-yourself) instead.

Open <http://localhost:8080>. Another port: set `FLOORBIT_PORT` in `.env`. Every line in `.env` is
optional, and `docker compose up -d` works without the file too.

To try it with a made-up hall full of players and traffic first, set `FLOORBIT_DEMO=1` in `.env`
and run `docker compose up -d` again ([demo.md](demo.md)).

## 2. The first account and setup

Open Floorbit in the browser and follow **Set up Floorbit**. It asks for the setup code that
Floorbit prints to its log while it has no accounts, so nobody else who reaches a new server first
can make themselves admin:

```sh
docker compose logs floorbit | grep "setup code"
```

The code changes on every restart and after 10 wrong tries. With it you create the first account
(an admin), then the setup walks you through NetBox, LibreNMS, importing switches and the look.
Every step can be skipped and done later in Settings; until you finish or skip to the end, the
floor plan sends admins back to it.

Without the browser, put a name and password in `.env` before the first start:

```sh
AUTH_ADMIN_USER=admin
AUTH_ADMIN_PASSWORD=a-long-password
```

or create the account in the running container (it asks for the password):

```sh
docker compose exec floorbit flask users add admin
```

Add more accounts under **Settings > Users**, or with
`docker compose exec floorbit flask users add <name> --role tech`. Roles and teams:
[auth.md](auth.md). If you used `.env`, take the password back out once you can sign in: it is only
read while there are no accounts. An install that already had switches, blocks or settings before
the setup existed counts as set up.

## 3. Your floor plan

Without NetBox, add switches and seat blocks with **Switch** (S) and **Seat block** (B) in the
floor plan's toolbar.
Everything you place is saved in the `floorbit_state` volume.

## 4. NetBox and LibreNMS

Both are optional and can be added at any time.

| Set in `.env` | What you get |
| --- | --- |
| `NETBOX_URL`, `NETBOX_TOKEN` (read-only token) | Switches come from NetBox; you only place them. `NETBOX_DEVICE_ROLE` picks the device roles (default `access-switch`). |
| `LIBRENMS_URL`, `LIBRENMS_TOKEN` (read-only token) | Live status, ports, traffic, and which seat is on which port. |

Then `docker compose up -d` to restart with them. With a self-signed certificate, add
`NETBOX_VERIFY_SSL=false` or `LIBRENMS_VERIFY_SSL=false`. **Settings** shows whether each answers,
and most settings (Discord, check-in, caching) can also be changed there; values saved there win
over `.env`. All variables: the table in the [README](../README.md#configuration) and
[integrations.md](integrations.md).

## 5. Behind a reverse proxy

Floorbit answers plain HTTP on the port above. Put a reverse proxy with TLS in front for anything
beyond a test. The proxy also reads each request whole before passing it on: without one, a hundred
connections from the event network that send their request a byte at a time hold all of gunicorn's
threads, and Floorbit stops answering until they give up. Then set in `.env`:

```sh
PUBLIC_URL=https://floor.example.com   # links in Discord messages, QR codes and sign-in providers
AUTH_COOKIE_SECURE=true                # the session cookie only travels over HTTPS
CHECKIN_TRUST_PROXY=true               # the client's address comes from X-Forwarded-For
```

Without `CHECKIN_TRUST_PROXY`, every visitor looks like the proxy: five wrong passwords from anyone
lock that username for everyone for five minutes. (Check-in doesn't depend on it: it takes the seat
PC's address only from the agent's front door, below.) Floorbit
logs a `[proxy]` hint when it sees this. Turn it on only when nothing but your proxy can reach
Floorbit's port: bind it to localhost (`FLOORBIT_PORT=127.0.0.1:8080`) or keep it off the
firewall. Otherwise anyone could send their own `X-Forwarded-For`. With a second proxy in front
(a CDN before nginx), also set `CHECKIN_PROXY_HOPS=2`.

Live updates are a long-running request (`/api/events`): don't buffer it (Floorbit already sends
`X-Accel-Buffering: no` for nginx) and allow it a long read timeout.

## 6. Syslog and traffic insights (optional)

The agent takes syslog on udp/514 (`SYSLOG_PUBLISH_PORT`, [syslog.md](syslog.md)) and NetFlow/IPFIX
for the **Traffic** page on udp/2055 (`FLOWS_PORT`, [flows.md](flows.md)). Point the switches,
firewalls and the router at this host. Floorbit turns the plugins for both (**Syslog from the
hall**, **Traffic from the hall**) and the **Front door for attendees** on for its agent the first
time it starts with it; change or turn them off under Settings > Plugins.

## Backups

Everything Floorbit keeps is in the `floorbit_state` volume (`/app/state`): the database
`floorbit.db` (floor plan, accounts, settings, the audit log, past events, plugin state and
check-ins), hall images, syslog and flow statistics ([database.md](database.md)). Valkey holds only a cache.
Older installs also have the JSON files Floorbit moved into the database on its first start after
the update; they are no longer read.

- **In the app:** **Settings > Backup and restore** downloads the floor plan and settings as one file, without
  accounts or tokens, and restores it on any Floorbit ([backup.md](backup.md)).
- **Everything:** copy the volume out. Stop Floorbit first, so the database file isn't copied
  halfway through a write:

  ```sh
  docker compose stop floorbit
  docker compose cp floorbit:/app/state ./floorbit-backup-$(date +%F)
  docker compose start floorbit
  ```

  To restore, copy it back, give the files to the app's user (`docker compose cp` makes them
  root's) and restart:

  ```sh
  docker compose cp ./floorbit-backup-2026-11-14/. floorbit:/app/state/
  docker compose exec -u root floorbit chown -R floorbit: /app/state
  docker compose restart floorbit
  ```

  If you forget the `chown`, the log says so when Floorbit starts, and saving fails until you run it.

## Updating

```sh
docker compose pull
docker compose up -d
```

`FLOORBIT_VERSION` in `.env` pins a release (`1.4.0`) instead of `latest` (the newest `master` that passed CI: the image is pushed only once CI is green on that commit).
Read the [changelog](../CHANGELOG.md) before a big jump. Your data stays in the volume.

The cache moved from Redis to Valkey, so the service is called `valkey` now. Run
`docker compose up -d --remove-orphans` once to stop the old `redis` container, and
`docker volume rm <project>_redis_data` if you like: it held only a cache, which Valkey fills again.

### From an older compose file

Before this guide, the compose file mounted `./data.json` and `./state` from the folder and called the
service `lal-app`. To move over, stop the old setup, start the new one once, and copy the old files in:

```sh
docker compose down                          # with the old docker-compose.yml
# replace docker-compose.yml with the new one, then:
docker compose up -d
docker compose cp ./data.json floorbit:/app/state/data.json
docker compose cp ./state/. floorbit:/app/state/
docker compose exec -u root floorbit chown -R floorbit: /app/state
docker compose restart floorbit
```

The app now runs as an unprivileged user, hence the `chown`. Check-ins, the audit log and plugin
state keep their old names inside `/app/state`. Redis is no longer published on port
6379, and the app answers on 8080 instead of 5002 (`FLOORBIT_PORT=5002` keeps the old port).

## Building the image yourself

From a clone of the repository:

```sh
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

## Good to know

- One process serves everything: the status monitor and the watchers live in it, so don't scale
  the `floorbit` service. Each open browser tab holds one of 64 threads for live updates, and 48 of
  them at most (24 for attendees who aren't signed in), so pages keep loading. For more screens,
  add `GUNICORN_CMD_ARGS=--threads 200` to `.env` (150 live tabs).
- `docker compose logs -f floorbit` shows what it is doing; `/healthz` answers when it is up.
- Set `TZ` in `.env` to the event's time zone (for example `TZ=Europe/Zurich`). Without it the
  container runs on UTC, and what the server works out by the clock itself is an hour or two
  off: quiet hours, the bandwidth forecast's hours, times on the public status page,
  and imported schedule times that carry no zone. The crew pages show times in each browser's
  own time zone either way.
- Keep the host's clock synced (NTP). If it is set back while Floorbit runs, cooldowns, lockouts and
  rate limits that started "in the future" end at once instead of lasting until the clock catches
  up; the replay recorder skips frames until then, so the timeline stays in order.
- A full disk (or a state folder mounted read-only) doesn't lose what was saved: each file is
  written whole beside the old one first. Until there is space again, pages keep showing the last
  saved state and every change answers "Floorbit's disk is full, so this change was not saved".
  The log says it once: `[store] Saving failed: No space left on device`.
