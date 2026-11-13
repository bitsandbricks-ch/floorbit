# Kiosk view

`/kiosk` is a read-only floor plan for a big screen at the event. It shows the
map scaled to fit the screen, switch status, which seats are taken, and a
"Down" list of switches that are offline and for how long. It never writes to
the server and has no editing controls.

## Options

Add them to the URL, for example `/kiosk?title=LAN%20Party&refresh=10`.

| Option    | Default      | What it does |
|-----------|--------------|--------------|
| `title`   | `Floor plan` | Heading in the top bar. |
| `refresh` | `15`         | Seconds between status polls when live updates are off (5 to 300). |
| `labels`  | `1`          | `0` hides switch names on the map. |
| `reload`  | `360`        | Reload the whole page every N minutes to pick up a new deployment (`0` = never). It only reloads when the server answers. |

## How it stays up to date

- **With live updates** (`/api/events` from the integrations MR): switch status
  changes, seat check-ins and layout edits arrive as pushes. The page still
  polls once a minute as a safety net. The top right shows "Live".
- **Without live updates**: it polls switch status every `refresh` seconds
  (from `/api/status/snapshot` when the status monitor runs, otherwise one
  `/api/switches/<id>/status` call per switch, like the editor does). The top
  right shows "Every 15s".
- The layout and seat occupancy reload every minute either way.
- If no update has succeeded for 90 seconds (or four poll intervals, whichever
  is longer), a red banner says the data may be out of date.

Seats count as taken when `/api/seats/info` has a username for them
(`seats.json`, or any seat source such as check-ins). Usernames are not shown
on the screen.

## On the screen

- Double-click or press `F` to toggle full screen. Chromium in kiosk mode
  (`chromium --kiosk http://host:5000/kiosk`) needs neither.
- The mouse pointer hides after 3 seconds.
- The page asks the browser to keep the screen awake (Screen Wake Lock), where
  the browser allows it.
