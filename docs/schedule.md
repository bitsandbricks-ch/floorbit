# Schedule and countdown

**Schedule** (`/schedule`) holds the event's programme: talks, tournaments, meals, quiet hours and
anything else, each with a start, an optional end, where and a note. Everyone signed in can read
it; changing it needs `floorplan.edit` (leads and admins). Changes are in the audit log.

**Event times** set when the event starts and ends. Before the start, the public page counts down
to it; after the end, it thanks everyone for coming.

## Importing iCal

**Import iCal** reads an `.ics` file from a calendar (Google Calendar, Outlook, Nextcloud) or the
event website: each event's title, start, end, location and description.

- **Kind:** guessed from the event's categories and title. "Turnier", "final" or "cup" make a
  tournament; "lunch", "Znacht" or "pizza" make food; "Nachtruhe" or "quiet" make quiet hours;
  "talk" or "workshop" make a talk.
- **Times:** taken with their time zone. Times without one are read in the browser's time zone.
  All-day events last the whole day.
- **Repeating events:** count once.
- **Importing again:** updates the items the last import brought in (matched by the file's UIDs) and
  removes the ones no longer in the file. Items added by hand stay.

## The public page

`/agenda` shows attendees the countdown, what is on now, what is next, a quiet-hours banner while
they last, and the programme day by day, in the reader's own time zone. `?screen=1` is the
big-screen layout. `/agenda.json` has the same for the event website or a Discord bot. The
attendee view (`/hall`) links to it.

It is off until **Settings > Attendee pages > Schedule and countdown** (or `SCHEDULE_PAGE=true`)
turns it on. It shows the programme only, never who planned it.

| Endpoint | What |
| --- | --- |
| `GET /api/schedule` | the event times and every item, with who changed it |
| `POST /api/schedule/items` | `{"title", "kind", "start", "end", "where", "note"}`, times in seconds since 1970 |
| `PATCH` / `DELETE /api/schedule/items/<id>` | change or remove one |
| `PUT /api/schedule/event` | `{"start", "end"}` |
| `POST /api/schedule/import` | `{"ics": "<file text>", "tz": "Europe/Zurich"}` |
