# Install with Docker Compose

Floorbit and Redis in two containers, on any machine with Docker. It works without NetBox or
LibreNMS: you place switches by hand and connect those later.

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
beyond a test, then set in `.env`:

```sh
PUBLIC_URL=https://floor.example.com   # links in Discord messages, QR codes and sign-in providers
AUTH_COOKIE_SECURE=true                # the session cookie only travels over HTTPS
```

Live updates are a long-running request (`/api/events`): don't buffer it (Floorbit already sends
`X-Accel-Buffering: no` for nginx) and allow it a long read timeout.

## Backups

Everything Floorbit keeps is in the `floorbit_state` volume (`/app/state`): `data.json` (floor plan,
accounts, settings), `audit.jsonl`, plugin state and check-ins. Redis holds only a cache.

- **In the app:** **Settings > Backup and restore** downloads the floor plan and settings as one file, without
  accounts or tokens, and restores it on any Floorbit ([backup.md](backup.md)).
- **Everything:** copy the volume out:

  ```sh
  docker compose cp floorbit:/app/state ./floorbit-backup-$(date +%F)
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

`FLOORBIT_VERSION` in `.env` pins a release (`1.4.0`) instead of `latest` (the newest `master`).
Read the [changelog](../CHANGELOG.md) before a big jump. Your data stays in the volume.

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
  the `floorbit` service. Each open browser tab holds one of 64 threads for live updates; for more
  screens, add `GUNICORN_CMD_ARGS=--threads 200` to `.env`.
- `docker compose logs -f floorbit` shows what it is doing; `/healthz` answers when it is up.
