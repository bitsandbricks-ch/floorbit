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

## Hosted: one tenant per process

On a hosted platform each tenant (club) runs its own Floorbit process: the same image with
`FLOORBIT_TENANT=<name>` (lower-case letters, digits and `-`, at most 40). The processes share one
database (`FLOORBIT_DATABASE_URL`, Postgres) and one Redis, and keep apart by name:

| What | Self-hosted | `FLOORBIT_TENANT=club-a` |
| --- | --- | --- |
| Tenant documents | `data.json`, `tenant.json`, ... | `tenants/club-a/data.json`, `tenants/club-a/tenant.json`, ... |
| Event documents | `event-data/<id>/...` | `tenants/club-a/event-data/<id>/...` |
| Redis keys and channels | as they are (`arp:...`, `floorbit:stats`) | `club-a:arp:...`, `club-a:floorbit:stats` |

Everything a tenant sets up is its own: accounts and roles, settings and the look (name, logo,
colours, Discord), the public status page, the check-in portal, plugins and local agents. Each
tenant reaches its Floorbit under its own host name (`club-a.floor.example.com`, set by the
platform's ingress), and its agent connects there. The flow collector of a tenant needs the same
`FLOORBIT_TENANT`.

A wrong `FLOORBIT_TENANT` stops Floorbit at start. Without it, nothing changes: a self-hosted
install is its own single tenant.

### Adding a tenant

There is no sign-up. Whoever runs the platform adds a tenant from any tenant's container (they all
share the storage) and then starts its process:

```
flask --app app tenants add club-b --name "Club B" --url https://club-b.floor.example.com --admin boss
flask --app app tenants list
```

The list of tenants is `platform.json`, beside `tenants/`. `--admin` adds the tenant's first admin
account (the password is asked for); without it the new tenant opens on its first-run setup.

### People in several tenants

A person has one account in each tenant, with that tenant's role, so a lead in one club can be a
viewer in another. Two accounts are the same person when they are linked to the same outside login:
the same Discord account, or the same subject at the same OIDC issuer. Usernames and passwords never
link accounts. Such a person finds their other tenants in the account menu (bottom of the sidebar,
"Your other clubs"), which opens the other tenant's address; signing in there uses the same login.
`GET /api/tenant/mine` answers the same list.

## For developers

Never build a path from `store.DATA_FILE`. Use:

- `store.tenant_path(name)` and `store.event_path(name)` for a document or folder of the current
  tenant or event;
- `store.tenant_file(configured)` and `store.event_file(configured)` for a file someone can
  configure (`CHECKIN_FILE`, `PLUGINS_FILE`): on the first event it stays exactly as configured,
  on a later one the same name goes into that event's folder;
- `store.load_data()` and `store.save_data()` for the current event's `data.json`.

Code runs for the live event unless it picks another one with `tenancy.using_event(event)`.
