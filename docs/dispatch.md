# Tech dispatch

Send an incident to the nearest free tech, and let techs work their jobs from their phone.

## For techs: My jobs

**My jobs** (`/jobs`, linked from the incident board) is made for a phone:

- **On duty:** only techs on duty get jobs sent to them. Turn it off for your break.
- **Where I am:** the seat you're next to. Each job you finish moves you to its seat (or switch), so
  you rarely need to set it by hand.
- Each job shows the hall plan with the seat marked in red, and a dashed line from where you are.
  The plan has no walls or aisles, so the line is the straight way, not a walking route.
- **On my way** tells the board you saw the job. **Done** marks the incident fixed (with an optional
  note). **Give back** puts it back on the board, unassigned, for someone else.

The page refreshes by itself when a job comes in.

## For leads: Send to nearest tech

On the incident board, **Send to nearest tech** (needs `incidents.assign` for the incident's team)
gives the incident to the free tech nearest to it:

- **free:** on duty, may work the incident's team (`incidents.work` in their role or the team), and
  no job they haven't finished or given back;
- **nearest:** the straight line on the floor plan from where they are to the incident's seat or
  switch. Someone in the same hall comes before anyone in another hall, and both before a tech who
  hasn't said where they are. Incidents on a power circuit have no place on the plan, so any free
  tech can get them; a tie goes to whoever has waited longest.

The board shows who is on duty, where, and how many jobs they have, and on each sent incident
whether the tech has seen it yet ("on the way") or not.

Nothing is sent by itself: a lead decides. Everything goes to the audit log (sent, taken, finished,
given back).

## What is kept

`data.json` keeps, per account under `dispatch`: on duty or not, the seat or switch they said they are
at, and since when. No GPS, no phone location: a position is always a seat number.

## API

| Request | Needs | What |
| --- | --- | --- |
| `GET /api/jobs` | `incidents.work` | My status, my jobs with the hall plan, the job's point and mine |
| `PUT /api/jobs/me` | `incidents.work` | `{"on_duty": true, "at": "B-7"}`; `"at": ""` clears it |
| `POST /api/jobs/<id>/take` | the job's tech | On my way |
| `POST /api/jobs/<id>/done` | the job's tech | Fixed, with an optional `note` |
| `POST /api/jobs/<id>/give-back` | the job's tech | Back on the board, with an optional `note` |
| `POST /api/incidents/<id>/dispatch` | `incidents.assign` | Send to the nearest free tech; 409 if there is none |
| `GET /api/dispatch/crew` | `incidents.assign` | Who is on duty, where, with how many jobs |
