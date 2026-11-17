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

Data in `data.json` that belongs to the tenant (accounts, settings, agents, dashboards, runbooks;
`store.TENANT_KEYS`) stays in the tenant's `data.json`. A later event's `data.json` holds only the
event's parts, and Floorbit reads and saves the two together.

## Which event a page shows

Every request works on the event in the `floorbit_event` cookie, else the live one. Add
`?event=<id>` to any page to pick one; it is remembered in the cookie. Kiosk screens and public
pages use the query. Answers carry the event in the `X-Floorbit-Event` header.

Changing the network (port actions, switch commands, the terminal, RCON) only works from the live
event: these always reach the live event's network, so from another event they answer
"This event isn't live".

## The API

| Call | Who | What |
| --- | --- | --- |
| `GET /api/tenant/events` | Everyone who sees the floor plan | The events, the live one and the current one |
| `PUT /api/tenant/current` `{"event": "<id>"}` | Everyone who sees the floor plan | Work on that event (`null`: follow the live one) |
| `POST /api/tenant/events` `{"name", "copy_from"?}` | Admins | A new event in planning, empty or with a copy of another event's plan |
| `PATCH /api/tenant/events/<id>` `{"name"?, "status"?}` | Admins | Rename, make live (the live one goes back to planning) or close |
| `POST /api/tenant/events/<id>/copy` `{"to", "parts"?, "mode"?, "preview"?}` | Admins | Copy parts of this event's plan into another event |

## Copying an event

A copy takes the parts you pick (all by default):

| Part | What it copies |
| --- | --- |
| `halls` | Halls and their background pictures |
| `seats` | Seat blocks and seats |
| `inventory` | Switches and devices, plan groups, plan marks, port areas, links |
| `cables` | Cables, cable routes, patch panels |
| `power` | Power boards and circuits |
| `services` | Firewalls, services, game servers |
| `schedule` | Schedule, tournament, brackets |

Check-ins, incidents, handover, logs and history are never copied. Tenant-wide parts are shared by
every event anyway.

Into an existing event, `mode` is `merge` (the default: things with the same id are replaced by the
copy, the target's others stay) or `replace` (the part becomes the source's). `"preview": true`
answers what would change per part (`added`, `changed`, `removed`) without saving.

## For developers

Never build a path from `store.DATA_FILE`. Use:

- `store.tenant_path(name)` and `store.event_path(name)` for a document or folder of the current
  tenant or event;
- `store.tenant_file(configured)` and `store.event_file(configured)` for a file someone can
  configure (`CHECKIN_FILE`, `PLUGINS_FILE`): on the first event it stays exactly as configured,
  on a later one the same name goes into that event's folder;
- `store.load_data()` and `store.save_data()` for the current event's `data.json`.

Code runs for the live event unless it picks another one with `tenancy.using_event(event)`.
