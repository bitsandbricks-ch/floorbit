# Audit log

**Logs > Audit log** (accounts with `audit.read`: admins and leads) lists who changed what, and when, newest first.

## What is logged

| Area | Entries |
| --- | --- |
| Floor plan | Switches added, changed (moved, renamed), deleted, NetBox syncs; seat blocks added, changed, deleted |
| Settings | Settings saved (which ones), a backup restored, the cache cleared, a Discord test message |
| Accounts | Accounts added, changed (role, name, password reset), deleted |
| Check-in | A check-in removed by an orga member, check-ins refreshed |
| Sign-in | Sign-ins, failed sign-ins (with the username that was tried), sign-outs |

Each entry has the time, the account, the action, what it was done to (a switch or seat block
name, a username) and which fields changed. It never holds the values: a saved API token shows up
as `netbox.token`, not the token, and passwords never appear. Reads and refused requests are not
logged, and neither are attendee check-ins, which have their own history.

Filter by area, account or any text, and download what you see as CSV.

## Where it is kept

One row per entry in the [database](database.md#logs), in the log named after `audit.jsonl` (next to
`data.json`, or `AUDIT_FILE`); an `audit.jsonl` from before the database is imported once. When the
log passes 2 MB the oldest half is dropped, which keeps tens of thousands of entries.

It is not in a backup (see [backup.md](backup.md)): it records what happened on this server.

## API

| Request | What it does |
| --- | --- |
| `GET /api/settings/audit?area=&user=&q=&limit=&offset=` | Entries, newest first, the total that match, and the areas to filter by. |
| `GET /api/settings/audit.csv?area=&user=&q=` | The same as a CSV download. |

The audit log can also be read on the Logs page, next to the syslog and Floorbit's own log, with
the same search ([syslog.md](syslog.md#floorbits-own-log-and-the-audit-log)).
