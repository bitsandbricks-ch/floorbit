# Kiosk view

`/kiosk` is a read-only floor plan for a big screen at the event. It shows the
map scaled to fit the screen, switch status, which seats are taken, and a
"Down" list of switches that are offline and for how long. It never writes to
the server and has no editing controls.

## Options

Add them to the URL, for example `/kiosk?title=LAN%20Party&refresh=10`.

| Option    | Default      | What it does |
|-----------|--------------|--------------|
| `title`   | event name, else `Floor plan` | Heading in the top bar. The event name is set under Settings > Appearance. |
| `theme`   | `kiosk`      | Theme preset for this screen, remembered by the browser ([docs/themes.md](docs/themes.md)). |
| `refresh` | `15`         | Seconds between status polls when live updates are off (5 to 300). |
| `labels`  | `1`          | `0` hides switch names on the map. |
| `view`    |              | `heat` colours each seat by its traffic right now (green a little, red a lot), from the [stats](stats.md) reads. Seat numbers and numbers only. |
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

Seats count as taken when a seat source (the seat mapping, `seats.json`,
check-ins) has a nick or IP for them. The kiosk asks `/api/seats/occupancy`,
which only lists the taken seats: nicks and IPs never reach the screen.

## On the screen

- Double-click or press `F` to toggle full screen. Chromium in kiosk mode
  (`chromium --kiosk http://host:5000/kiosk`) needs neither.
- The mouse pointer hides after 3 seconds.
- The page asks the browser to keep the screen awake (Screen Wake Lock), where
  the browser allows it.

## Other big screens

The [health wall](health.md) (`/health?screen=1`) and the [stats dashboard](stats.md)
(`/stats?screen=1`) have big-screen versions too, with the same kiosk theme and no personal data.

## Rotating views with a seat finder

`/screen` shows one view at a time and moves on every `every` seconds, with a QR code in the
corner that opens the seat finder on a phone. Sign the screen in with a `kiosk` account, like
`/kiosk`.

| Option  | Default            | What it does |
|---------|--------------------|--------------|
| `views` | `floor,heat,stats` | Which views, in order: `floor` (`/kiosk`), `heat` (`/kiosk?view=heat`), `stats` (`/stats?screen=1`), `health` (`/health?screen=1`). |
| `every` | `30`               | Seconds per view (10 to 600). |
| `qr`    | `1`                | `0` hides the QR code. |
| `theme` |                    | Theme preset for every view ([themes.md](themes.md)). |

Each view stays loaded after its first turn, so it keeps its live updates, and the next one loads
before it fades in. The QR code points at `PUBLIC_URL/find`, so set `PUBLIC_URL`
([install.md](install.md)) to an address players' phones can reach.

## Find your seat

`/find` is for players' phones and needs no account. They type the seat number from their ticket
and see where it is: the block, the row, the seat from the left, and the hall plan with the seat
marked. It shows seat blocks only, never who sits where. Lookups are limited to 30 a minute per
address.

| Setting | Default | |
|---------|---------|---|
| `SEAT_FINDER` | `true` | `false` switches the page off (and the QR code on `/screen`). |
| `SEAT_FINDER_NICKS` | `false` | Also find a seat by the player's exact nick. Off by default: anyone who knows a nick could find where that person sits. |


## Attendee view

`/hall` shows the hall plan with every seat green when it is online (its switch port is up) and grey
when it is not, plus "312 of 400 seats online". It needs no account, so it can go on the event website
or a screen at the entrance, and it works on phones in English and German.

It shows seat numbers and online or offline, nothing else: no nicks, addresses, MACs, switches or ports.
It is **off by default**, because it also shows when a seat is empty, for example while its player is
away. Switch it on under **Settings > Attendee pages** (or `ATTENDEE_VIEW=true`).

- The status comes from the same port reads as the stats page (every `ATTENTION_INTERVAL`, 120 s),
  so no extra requests go to the switches.
- The page reloads the status every minute from `GET /api/public/seats`
  (`{"seats": {"D-6": true, ...}, "online": 1, "total": 8, "updated": <unix time>}`).
- After three missed reads the page says the status isn't available instead of showing old dots, and
  the API answers `null` for every seat.
