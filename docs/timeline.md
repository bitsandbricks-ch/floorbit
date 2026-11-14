# Event changelog

`/timeline` (Settings › Event changelog) puts everything that changed during the LAN on one
timeline, newest first and grouped by day. Issue #100.

| Kind | What | From |
| --- | --- | --- |
| Changes | Floor plan, inventory, settings, accounts and plugin edits, with who and which fields (never the values) | the [audit log](audit.md) |
| Sign-ins | Who signed in (hidden unless picked) | the audit log |
| Outages | A switch going offline and coming back, with how long it was down | the status monitor's history, kept since the last new event ([report](report.md)) |
| Incidents | Opened and fixed | the incident board |
| Alerts | Security findings, power alerts, service health changes, the bandwidth forecast, log alerts, and the monitoring source going away and coming back | written as they happen (see below) |
| Deploys | Each start of Floorbit with its version, and "updated from 1.4.0 to 1.5.0" when the version changed | written at start |

Pick the kinds (each chip shows how many entries match), search (what, where or who) and the time
range: the last 6 hours, the last 24 hours, or everything. **Older entries** pages back 300 at a time.

## Export

**CSV** (`time,kind,title,target,who`) and **JSON** both export what the filters show, up to 2000
entries. For the whole audit log with every field, use Settings › Audit log.

## The journal

Alerts only pass by on Floorbit's event bus, so the changelog writes them to `timeline.jsonl` next to
`data.json` (or `TIMELINE_FILE`) as they happen, with each start of Floorbit. Alerts are written in
the same words webhooks get, which leave out MACs, IPs, nicks and log lines. Past 2 MB, the oldest
half is dropped.

Nothing else is copied: changes, outages and incidents are read from where they are kept, so the
changelog starts with what those kept (the audit log since it last trimmed itself, outages since the
last new event).

## Who can see it

It contains the audit log with names, so it needs `audit.read` (leads and admins by default).
Settings › Features has a `timeline` switch.

## API

- `GET /api/timeline?kinds=change,outage&q=&hours=24&before=<unix time>`: `entries` (each with `t`,
  `kind`, `title`, and `target`, `who`, `severity` where known), `total`, `counts` per kind, and `more`.
- `GET /api/timeline?format=json&...`: the same as a download, up to 2000 entries.
- `GET /api/timeline.csv?...`
