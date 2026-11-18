# Tenants and events

Floorbit runs several events, and on a hosted platform several organisations (issue #466). This
page says how state is split up.

Every Floorbit is a platform with at least one tenant, `default`. A self-hosted install is simply a
platform nobody added a second tenant to: it runs the same code as a hosted one, and nothing about
tenants shows until there are two. On the upgrade nothing moves: the default tenant keeps its
documents where every install always kept them.

## The model

| Level | What it is | Where its documents live |
| --- | --- | --- |
| Tenant | An organisation on the platform | `default`: the state folder (`/app/state` in Docker). Others: `tenants/<id>/` |
| Event | One LAN party the tenant runs | The first event: the state folder too. Later events: `event-data/<id>/` |

**Tenant documents:** accounts, roles, teams, API tokens, sign-in providers, settings and the look,
plugins (`plugins.json`), the audit log, floor plan templates, archived event records, the crew
Discord state, and the event list, `tenant.json`.

**Event documents:** the floor plan (`data.json`), halls, check-ins and their history, seat PINs and
learned seat ports, the timeline, the whole-event recording, syslog, flow, DNS and LANcache figures,
config backups and the last good monitoring data.

In the database ([database.md](database.md)), the folder is the start of the document's key, so
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
| `schedule` | Schedule, tournament |

Check-ins, incidents, handover, logs and history are never copied. Tenant-wide parts are shared by
every event anyway.

Into an existing event, `mode` is `merge` (the default: things with the same id are replaced by the
copy, the target's others stay) or `replace` (the part becomes the source's). `"preview": true`
answers what would change per part (`added`, `changed`, `removed`) without saving.

## One tenant per process

Each Floorbit process serves one tenant: the one named by `FLOORBIT_TENANT` (lower-case letters,
digits and `-`, at most 40), else `default`. A self-hosted install doesn't set it. On a hosted
platform each tenant runs its own process from the same image; the processes share one
database (`FLOORBIT_DATABASE_URL`, Postgres) and one Redis, and keep apart by name:

| What | `default` (self-hosted) | `FLOORBIT_TENANT=tenant-a` |
| --- | --- | --- |
| Tenant documents | `data.json`, `tenant.json`, ... | `tenants/tenant-a/data.json`, `tenants/tenant-a/tenant.json`, ... |
| Event documents | `event-data/<id>/...` | `tenants/tenant-a/event-data/<id>/...` |
| Redis keys and channels | `default:arp:...`, `default:floorbit:stats` | `tenant-a:arp:...`, `tenant-a:floorbit:stats` |

The default tenant's folder is the state folder itself, so the other tenants' folders sit inside
it. Its code never reaches into them: document listings read one folder level, and every document
it opens has its own name. Redis only holds a cache, so the prefix the default tenant got on the
upgrade costs a cache that fills again within a minute.

**How a request finds its tenant:** by the process it reaches. The platform's ingress sends each
tenant's host name (`tenant-a.floor.example.com`) to that tenant's processes, so a request never
names a tenant itself and can't ask for another one.

Everything a tenant sets up is its own: accounts and roles, settings and the look (name, logo,
colours, Discord), the public status page, the check-in portal, plugins and local agents. Each
tenant reaches its Floorbit under its own host name (`tenant-a.floor.example.com`, set by the
platform's ingress), and its agent connects there. The flow collector of a tenant needs the same
`FLOORBIT_TENANT`.

A wrong `FLOORBIT_TENANT` stops Floorbit at start.

### Adding and suspending tenants

There is no sign-up. The platform's admins are the admins of the default tenant: they find
**Settings > Tenants** (`/settings/tenants`) in the sidebar, and no other tenant has that page.
There they add a tenant (short name, name, address and optionally a first admin, whose
password is shown once), rename it, and **suspend** it. A suspended tenant's processes answer 503
"This tenant is suspended" to everything within 10 seconds, its login page and its agents included;
only `/healthz` stays open so Kubernetes doesn't restart it. Its data stays, and **Take back**
lets it in again. The default tenant can't be suspended. The same works from the command line in
any tenant's container (they all share the storage):

```
flask --app app tenants add tenant-b --name "Tenant B" --url https://tenant-b.floor.example.com --admin boss
flask --app app tenants list
```

The list of tenants is `platform.json`, beside `tenants/`. The default tenant is always on it,
first; the file itself appears when the second tenant is added. `--admin` adds the tenant's first admin
account (the password is asked for); without it the new tenant opens on its first-run setup.

Each tenant sets its own look under Settings (name, logo, colours, Discord): they are the
tenant's settings, so the platform page doesn't touch them.

### People in several tenants

A person has one account in each tenant, with that tenant's role, so a lead in one tenant can be a
viewer in another. Two accounts are the same person when they are linked to the same outside login:
the same Discord account, or the same subject at the same OIDC issuer. Usernames and passwords never
link accounts.

### Switching tenants

When someone can reach another tenant, a tenant switcher shows at the bottom of the sidebar, above
the account menu. Nobody on a platform with one tenant (every self-hosted install) ever sees it.
It lists:

- the tenants where the person has a linked account (above), where they arrive as that account;
- for admins of the default tenant (the platform admins), every other active tenant, where they
  arrive as `platform:<their name>`, an admin who has no account there. Each request checks that they
  are still an admin of the default tenant, and a visit ends after 8 hours. The tenant's audit log
  shows "Came in from another tenant" with that name, so its own admins see the visit.

Only tenants with an address (Settings > Tenants) show up: that is where the browser goes.

Switching doesn't ask for the password again. The tenant you leave writes a one-time ticket into
the tenant you go to (stored under its hash, in `handoffs/`, good for 60 seconds) and sends the
browser to `<address>/switch/arrive?ticket=...`; that tenant takes the ticket, deletes it, and signs
the browser in. A ticket works once, only in the tenant it was written for, and only while the
link or the admin role that made it is still there. API tokens and visitors can't switch on.

- `GET /api/tenant/mine`: the tenants the signed-in person can switch to, with `how`
  (`account` or `platform`).
- `POST /api/tenant/switch` `{"tenant": "<id>"}`: `{"url"}`, where to send the browser.

## For developers

Never build a path from `store.DATA_FILE`. Use:

- `store.tenant_path(name)` and `store.event_path(name)` for a document or folder of the current
  tenant or event;
- `store.tenant_file(configured)` and `store.event_file(configured)` for a file someone can
  configure (`CHECKIN_FILE`, `PLUGINS_FILE`): on the first event it stays exactly as configured,
  on a later one the same name goes into that event's folder;
- `store.load_data()` and `store.save_data()` for the current event's `data.json`.

Code runs for the live event unless it picks another one with `tenancy.using_event(event)`.

## What keeps tenants apart

Tenants on one platform share the database, Redis and often the S3 bucket and `SECRET_KEY`.
`tests/test_tenant_isolation.py` plays several tenants in one process and tries to cross over:

| What | How it stays the tenant's own |
| --- | --- |
| Documents | Every path comes from `store.tenant_path`/`event_path`, so from the tenant's folder; a configured file (`MONITORING_CACHE_FILE`, `AUDIT_FILE`, ...) goes into it too |
| Sign-in | The session cookie names the tenant that signed it in; another tenant drops it, even with the same `SECRET_KEY` and username |
| Switching tenants | A hand-off ticket is written into one tenant's folder, works once and only there, and a platform visit is re-checked against the default tenant on every request |
| API tokens, agent keys | Kept in the tenant's accounts and agent list, so another tenant doesn't know them |
| Redis keys and live updates | Prefixed with the tenant's name; the live-update channel too |
| S3 backups | Each tenant lists, prunes and restores only its own folder |
| Seat help links | Signed with the tenant's name (the default tenant's as before, so printed cards keep working) |
