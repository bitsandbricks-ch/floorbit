# Events

Issue #38. Every event is kept as its own record. The **Events** row in the sidebar (`/events`,
issue #1201) lists them, with the event's own pages (schedule, changelog, replay, report,
templates) as its tabs. The archive of past events and the side-by-side comparison follow the
**Past events** feature; the event list itself is always there.

## Planning the next event

The **Events** box at the top of the page lists the events of this install: one is **Live**, the
others are in **Planning** or **Closed** (see [Tenants and events](tenancy.md)).

- **Open** works on that event in this browser. Every crew page then shows a banner with the event's
  name and **Back to the live event**. Port actions, switch commands and the terminal only work from
  the live event.
- **New event** (admins) starts one in planning, with an empty floor plan or a copy of another
  event's.
- **Copy event** (admins) copies parts of one event's floor plan into a new or an existing event:
  halls, seats, inventory, cables, power, services, schedule. Into an existing event, **Preview**
  first shows what changes, then **Copy** merges or replaces. Check-ins, incidents, handover, logs
  and history are never copied.
- **Make live** switches monitoring, the agent and the network actions to that event; the live one
  goes back to planning.

## Closing an event

When the event is over, an admin (**Change settings**) closes it at the bottom of the events page. To
make sure it isn't a stray click, the event's name (Settings > Theme) has to be typed; an event with
no name asks for `close`. A name for the next event can be given and becomes the theme's event name.

Closing:

1. **Keeps the event** as a file in `events/` next to `data.json`: its report (the same one as
   `/report`, without nicks or IPs), its floor plan as a backup (like Settings > Backup, no secrets or
   accounts) and the key figures.
2. **Starts the next one from it.** These stay: the floor plan and inventory, the settings, and
   accounts and teams.
3. **Begins these again:** the report's history and the bandwidth peak (like *Start a new event* on the
   report), incidents, shift handovers and pre-flight results.

The file is written first. If that fails, nothing is cleared. Closing goes to the audit log.

Download the incident board as a spreadsheet (**Download as CSV** on the Incidents page) before closing
if you want it as a file: the archived record keeps the report, which counts the incidents, but not
the board itself.

## Comparing

For the running event and every closed one:

| Figure | From |
| --- | --- |
| Most seats online, most checked in | the report's hours |
| Peak bandwidth, data moved | the stats store (data moved is estimated from hourly averages) |
| Incidents, median time until someone takes it, median time to fix | the incident board |
| Switch outages, downtime in all | the status monitor's switch changes |
| Cache savings | empty until a game cache source reports them (#88) |

A bar under each figure shows it against the largest in its row.

## Per past event

- **Report**: the report PDF, in the page's language and time zone. Anyone who can see the floor plan.
- **Floor plan**: the backup file; restore it under Settings > Backup to set up a hall the same way
  again. Admins only.
- **Rename** and **Delete**: admins only, both in the audit log.

## API

| Request | Permission |
| --- | --- |
| `GET /api/past-events` | See the floor plan |
| `GET /api/past-events/<id>/report.pdf?lang=&tz=` | See the floor plan |
| `GET /api/past-events/backup/<id>.json` | Change settings |
| `POST /api/past-events/close` `{"confirm", "next_name"}` | Change settings |
| `PATCH /api/past-events/<id>` `{"name"}`, `DELETE /api/past-events/<id>` | Change settings |

Event ids are `YYYYMMDD-<8 hex>`. Anything else is a 404, so an id can never reach outside `events/`.

Compose keeps `events/` in the state folder with `data.json` (see docs/install.md), so it survives updates.
