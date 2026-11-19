# Schedule

**Schedule** (`/schedule`) holds the event's programme: talks, tournaments, meals, quiet hours and
anything else, each with a start, an optional end, where and a note. Everyone signed in can read
it; changing it needs `floorplan.edit` (leads and admins). Changes are in the audit log.

**Event times** set when the event starts and ends. Seat ports learned on the
[seat walk-through](seat-walk.md) are cleared a day after the end.

The [shift handover](handover.md) lists the items that start during the next shift. The schedule is
for the crew: there is no public agenda page and no programme channel on Discord.

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

## API

| Endpoint | What |
| --- | --- |
| `GET /api/schedule` | the event times and every item, with who changed it |
| `POST /api/schedule/items` | `{"title", "kind", "start", "end", "where", "note"}`, times in seconds since 1970 |
| `PATCH` / `DELETE /api/schedule/items/<id>` | change or remove one |
| `PUT /api/schedule/event` | `{"start", "end"}` |
| `POST /api/schedule/import` | `{"ics": "<file text>", "tz": "Europe/Zurich"}` |
