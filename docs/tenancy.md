# Tenants and events

Floorbit is getting ready to run several events, and on a hosted platform several organisations
(issue #466). This page says how state is split up. Today it changes nothing for an install: there
is one tenant with one live event, and every document is where it always was.

## The model

| Level | What it is | Where its documents live |
| --- | --- | --- |
| Tenant | A club or organisation | The state folder (`/app/state` in Docker) |
| Event | One LAN party the tenant runs | The first event: the state folder too. Later events: `event-data/<id>/` |

**Tenant documents:** accounts, roles, teams, API tokens, sign-in providers, settings and the look,
plugins (`plugins.json`), the audit log, floor plan templates, archived event records, the crew
Discord state, and the event list, `tenant.json`.

**Event documents:** the floor plan (`data.json`), halls, check-ins and their history, seat PINs and
learned seat ports, the timeline, the whole-event recording, syslog, flow, DNS and LANcache figures,
config backups and the last good monitoring data.

In a database (`FLOORBIT_DATABASE_URL`), the folder is the start of the document's key, so
`event-data/lan-2027/data.json` is a row of its own next to `data.json`.

## The event list

`tenant.json` lists the tenant's events. Without it, the tenant has one event, `main`, which is
live and kept in the tenant's folder.

```json
{"events": [
  {"id": "main", "name": "LAN 2026", "status": "closed"},
  {"id": "lan-2027", "name": "LAN 2027", "status": "live"}
]}
```

- `id`: lower-case letters, digits and `-`, at most 40 characters. It names the event's folder.
- `status`: `planning`, `live` or `closed`. Exactly one event is live: the background jobs, the
  agent and live monitoring serve it. With none or several, the first live one (or the first event)
  wins.

Creating events, switching between them and making one live come in the next steps; until then
`tenant.json` is only read.

## For developers

Never build a path from `store.DATA_FILE`. Use:

- `store.tenant_path(name)` and `store.event_path(name)` for a document or folder of the current
  tenant or event;
- `store.tenant_file(configured)` and `store.event_file(configured)` for a file someone can
  configure (`CHECKIN_FILE`, `PLUGINS_FILE`): on the first event it stays exactly as configured,
  on a later one the same name goes into that event's folder;
- `store.load_data()` and `store.save_data()` for the current event's `data.json`.

Code runs for the live event unless it picks another one with `tenancy.using_event(event)`.
