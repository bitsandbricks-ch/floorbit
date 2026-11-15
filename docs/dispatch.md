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

The page refreshes by itself when a job comes in, and the browser tab shows how many jobs you haven't
answered with **On my way** yet, like "(2) My jobs". Once you have fixed something, it also says how many
jobs you fixed in the last 12 hours, about one shift.

## For leads: Send to nearest tech

On the incident board, **Send to nearest tech** (needs `incidents.assign` for the incident's team)
gives the incident to the free tech nearest to it:

- **free:** on duty, may work the incident's team (`incidents.work` in their role or the team), and
  no job they haven't finished or given back;
- **nearest:** the straight line on the floor plan from where they are to the incident's seat or
  switch. Someone in the same hall comes before anyone in another hall, and both before a tech who
  hasn't said where they are. Incidents on a power circuit have no place on the plan, so any free
  tech can get them; a tie goes to whoever has waited longest.

The board shows who is on duty, where, how many jobs they have and how many they fixed in the last
12 hours, and on each sent incident whether the tech has seen it yet ("on the way") or not. A job nobody has seen 5 minutes after it
was sent says so in amber ("not seen for 7 min"): their phone may be in a pocket, and a lead can
send it to someone else. Click a
tech to filter the board to what they are on (`with:kim`); click again to clear it.

By default nothing is sent by itself: a lead decides. A lead (`incidents.assign`) can turn on
**Send new ones to the nearest free tech by themselves** next to the crew. Then every new incident
(from the board, a seat's help page or a power alert) goes to the nearest free tech the moment it is
filed, by the same rules. If nobody is free it stays on the board; incidents filed earlier are left
alone, so a tech coming back on duty is not flooded with old jobs at once. While it is on, My jobs tells
techs on duty that jobs come by themselves.

Everything goes to the audit log (sent by hand or by itself, taken, finished, given back, and the
switch turned on or off).

## What is kept

`data.json` keeps, per account under `dispatch`: on duty or not, the seat or switch they said they are
at, and since when. No GPS, no phone location: a position is always a seat number.

## API

| Request | Needs | What |
| --- | --- | --- |
| `GET /api/jobs` | `incidents.work` | My status, my jobs with the hall plan, the job's point and mine, and `done` (fixed in the last 12 hours) |
| `PUT /api/jobs/me` | `incidents.work` | `{"on_duty": true, "at": "B-7"}`; `"at": ""` clears it |
| `POST /api/jobs/<id>/take` | the job's tech | On my way |
| `POST /api/jobs/<id>/done` | the job's tech | Fixed, with an optional `note` |
| `POST /api/jobs/<id>/give-back` | the job's tech | Back on the board, with an optional `note` |
| `POST /api/incidents/<id>/dispatch` | `incidents.assign` | Send to the nearest free tech; 409 if there is none |
| `PUT /api/dispatch/auto` | `incidents.assign` | `{"on": true}`: send new incidents by themselves |
| `GET /api/dispatch/crew` | `incidents.assign` | Who is on duty, where, with how many open jobs and how many fixed in the last 12 hours (`done`), and whether `auto` is on |
