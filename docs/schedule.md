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
big-screen layout. `/agenda.json` has the same for the event website or a Discord bot.
`/agenda.ics` is the programme as a calendar feed: attendees subscribe to it on their phone (the
"Add the programme to your calendar" link under the page), and their calendar app fetches it again
every hour, so moved talks show up there too. Times are in UTC, so every app shows the reader's own
zone. Quiet hours come along but don't mark anyone as busy.

It is off until **Settings > Attendee pages > Schedule and countdown** (or `SCHEDULE_PAGE=true`)
turns it on. It shows the programme only, never who planned it.

| Endpoint | What |
| --- | --- |
| `GET /api/schedule` | the event times and every item, with who changed it |
| `POST /api/schedule/items` | `{"title", "kind", "start", "end", "where", "note"}`, times in seconds since 1970 |
| `PATCH` / `DELETE /api/schedule/items/<id>` | change or remove one |
| `PUT /api/schedule/event` | `{"start", "end"}` |
| `POST /api/schedule/import` | `{"ics": "<file text>", "tz": "Europe/Zurich"}` |

## Discord

Set **Settings > Discord > Attendee programme channel webhook** (`DISCORD_SCHEDULE_WEBHOOK_URL`) to a
webhook in a channel attendees read, such as `#announcements` (the status channel's webhook works too).
Ten minutes before an item starts (`SCHEDULE_ANNOUNCE_MINUTES`), Floorbit posts it there once:

- the title, where, the note, and when it starts as a Discord timestamp, so everyone reads their own time;
- items that start together share one message; quiet hours read "Quiet hours start in 10 minutes. Please keep it down.";
- an item moved to a new time is announced again at the new time;
- an item added less than ten minutes before it starts is announced right away.

Only while the public schedule page is on, and only what the page shows. Nobody is mentioned. What
was announced is kept in memory, so after a restart an item inside the window may come a second time.
