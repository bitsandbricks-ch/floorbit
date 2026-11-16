# Database: files, SQLite or Postgres

Floorbit keeps its state as a set of documents: `data.json` (the floor plan, accounts and
settings), saved floor plan templates, past events, plugin state, check-ins and the last good
monitoring data. Where they live is one setting, `FLOORBIT_DATABASE_URL`:

| `FLOORBIT_DATABASE_URL` | Where documents live | For |
| --- | --- | --- |
| *(not set)* | JSON files in the state folder (`/app/state` in Docker) | the default; small self-hosted setups |
| `sqlite:////app/state/floorbit.db` | one SQLite file | one server; the flow collector and the web app can share it safely |
| `postgresql://floorbit:password@db.example.com/floorbit` | a Postgres database | hosted Floorbit, a managed database, backups by your DBA |

Note the four slashes for an absolute SQLite path (`sqlite:///` + `/app/state/floorbit.db`).
Postgres needs the `psycopg` package, which the Docker image has.

## Switching from files

Set `FLOORBIT_DATABASE_URL` and restart. Nothing else is needed:

- The first time Floorbit reads a document the database doesn't have yet, it **imports it from its
  file**, once. Your floor plan, accounts and settings are all there after the restart.
- After that the file is no longer read or written. It stays where it was, so it doubles as a
  backup of the moment you switched. Delete it when you're happy.
- Going back to files: unset the variable. Floorbit uses the files again, as they were when you
  switched; changes made while on the database stay in the database. To take them along, make a
  backup under **Settings > Backup and restore** first and restore it afterwards.

## What stays in the state folder

The database holds the documents above. These are still files in the state folder, so **keep a
volume on it** even with a database ([kubernetes.md](kubernetes.md#keep-the-volume)):

- hall background images,
- syslog and flow statistics.

## Logs

The audit log, the event timeline, the check-in history and the event recording are in the
database too, in the table `floorbit_log`, so every Floorbit pod writes the same log and a replaced
container loses nothing. Like documents, each log is imported from its `.jsonl` file the first
time it is used, once; the file then stays as a backup. Without a database they are `.jsonl`
files in the state folder, as before.

## Schema and migrations

Floorbit creates its tables itself, on the first connection. Each schema change is a numbered step
that runs once and is recorded in the table `floorbit_schema`; all steps run in one transaction,
so a failed step leaves nothing behind. Two processes starting at the same moment (the web app and
the flow collector) take turns. The same steps run on SQLite and Postgres.

## Health

At start Floorbit waits up to 10 seconds (`FLOORBIT_DATABASE_WAIT`) for the database, for a
database container that comes up a little after it.

## When the database is away

Floorbit keeps running without its database, whether it went away while running or wasn't there at
the start, and comes back by itself:

- **Reading** goes on from the last copy of each document this process read or saved, so the
  floor plan, the Seats view, the problems list and the big screens keep working. Live status from
  LibreNMS, the agents and Redis doesn't need the database and keeps updating.
- **Saving** is refused with `503` and `{"code": "database_unavailable"}` and a clear message
  (in German for German readers); nothing is queued or half saved. A document Floorbit hasn't read
  yet answers the same, never an empty one in its place. A page that needs one shows a short
  "Database unavailable" page that reloads itself every 10 seconds.
- **The crew pages** show a banner while it is away and "Database back" once it answers again.
- **Trying again**: the first try after 1 second, then the wait doubles up to 30 seconds. Between
  tries, requests don't wait on the database at all. While it answers, Floorbit asks it every
  15 seconds in the background, so the banner and `/healthz` notice an outage without a request.
- **Counters** that keep their counts in the database (DNS, LAN cache) wait until they have read
  them, so they never save a count that started from nothing over the stored one.

Started without the database, nothing has been read yet: signing in, and most pages, wait until it
is back. Set `SECRET_KEY` (the Kubernetes example does), so sessions signed before stay valid even
then; without it the generated key lives in the database too.

`GET /healthz` stays `200` and says `"database": "down"` with how long, because Floorbit keeps
serving and a restart wouldn't bring the database back. So Docker and Kubernetes leave it running
instead of restarting it in a loop. `GET /healthz?strict=1` answers `503` while the database is
away, for a load balancer that has another instance to send people to.

The log says where documents are kept, with the password left out, and when the database goes
away and comes back:

```
[store] Keeping documents in postgres (postgresql://floorbit:***@db.example.com/floorbit)
[store] The database postgres (...) doesn't answer (...). Pages show the last copies read and saving is off until it is back; trying again in the background.
[store] The database answers again after 42 s.
```

A dropped connection (a restart, a failover) is reopened once per request before it counts as away.

## Tests

The suite runs on files by default. `FLOORBIT_TEST_DATABASE=sqlite pytest` runs it on a fresh
SQLite file per test, and `FLOORBIT_TEST_DATABASE=postgres` on the database in
`FLOORBIT_TEST_POSTGRES_URL` (emptied before each test). CI runs all three.
