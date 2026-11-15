# Runbooks

Runbooks are step-by-step fix guides for kinds of incident: no internet at the seat, a slow
connection, no power, a switch down. Leads write them in Floorbit; techs read them where they work.

- On the **incident board**, an incident links to the runbook for its kind.
- On the tech's **job page** (`/jobs`), the steps open right on the job.
- **Runbooks** (`/runbooks`, also from the incident board and Settings) lists them all.

## Kinds of incident

| Kind | Which incidents |
| --- | --- |
| No internet | attendees who picked "no internet" on the help page |
| Slow connection | attendees who picked "slow" |
| Power | attendees who picked "no power", and incidents on a power circuit |
| Switch down | incidents on a switch without a seat |
| Other | everything else, including incidents filed on the board for a seat |

A runbook can be for several kinds, or none (then it is only on the Runbooks page). When more than
one runbook is for a kind, the one highest in the list is used; move them up and down to choose.

## Starters

Until the crew saves a runbook, Floorbit offers four starters with general first steps. Saving,
adding or removing any runbook keeps the list as it is from then on. Rewrite the starters with your
event's own steps: where the spare switches and cables are, who to call, which channel to post in.

## Writing

Runbooks are Markdown: `#` headings, `1.` numbered steps, `-` bullets, `**bold**`, `` `code` `` and
`[links](https://example.com)`. Floorbit draws them itself and never runs HTML from them.

## Who may

- Reading needs `incidents.work` (techs, leads, admins).
- Writing, moving and deleting needs `incidents.assign` (leads and admins).
- Every change is in the audit log (area *runbooks*).

## API

| Route | What |
| --- | --- |
| `GET /api/runbooks` | the runbooks, in order, and the kinds |
| `POST /api/runbooks` | `{"title": "...", "kinds": ["no-internet"], "body": "1. ..."}` |
| `PATCH /api/runbooks/<id>` | change any of those |
| `DELETE /api/runbooks/<id>` | remove one |
| `POST /api/runbooks/<id>/move` | `{"step": -1}` moves it up, `1` down |

Incidents on `GET /api/incidents` carry `runbook: {id, title}`; jobs on `GET /api/jobs` carry the
runbook with its `body`.
