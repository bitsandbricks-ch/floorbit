# Past events

Issue #38. Every event is kept as its own record, and the events page (`/events`, linked from the
report) compares them side by side.

## Closing an event

When the event is over, an admin (**Change settings**) closes it at the bottom of the events page. To
make sure it isn't a stray click, the event's name (Settings > Theme) has to be typed; an event with
no name asks for `close`. A name for the next event can be given and becomes the theme's event name.

Closing:

1. **Keeps the event** as a file in `events/` next to `data.json`: its report (the same one as
   `/report`, without nicks or IPs), its floor plan as a backup (like Settings > Backup, no secrets or
   accounts) and the key figures.
2. **Starts the next one from it.** These stay: the floor plan and inventory, the settings, the build
   plan, accounts and teams, and the teardown steps the team added (unticked again). Gear that is still
   checked out stays out, because it is still somewhere.
3. **Begins these again:** the report's history and the bandwidth peak (like *Start a new event* on the
   report), incidents, shift handovers, pre-flight results, the teardown's switch and export ticks, and
   the gear log.

The file is written first. If that fails, nothing is cleared. Closing goes to the audit log.

Download the teardown export (`/teardown`) before closing if you want the incidents and handovers as
files: the archived record keeps the report, which counts them, but not the incident board itself.

## Comparing

For the running event and every closed one:

| Figure | From |
| --- | --- |
| Most seats online, most checked in | the report's hours |
| Peak bandwidth, data moved | the stats store (data moved is estimated from hourly averages) |
| Incidents, median time to fix | the incident board |
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
| `GET /api/events` | See the floor plan |
| `GET /api/events/<id>/report.pdf?lang=&tz=` | See the floor plan |
| `GET /api/events/backup/<id>.json` | Change settings |
| `POST /api/events/close` `{"confirm", "next_name"}` | Change settings |
| `PATCH /api/events/<id>` `{"name"}`, `DELETE /api/events/<id>` | Change settings |

Event ids are `YYYYMMDD-<8 hex>`. Anything else is a 404, so an id can never reach outside `events/`.

Compose keeps `events/` in the state folder with `data.json` (see docs/install.md), so it survives updates.
