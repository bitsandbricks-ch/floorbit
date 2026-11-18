# Kiosk and big screens

The big screen in the hall is the ready-made **Kiosk** [dashboard](dashboards.md): the floor plan
fitted to the screen with switch status and which seats are online, and beside it how many switches
are up, how many seats are online, and which switches are down and for how long. Open
`/dashboards/kiosk`, or the old address `/kiosk`, which goes there.

The Kiosk dashboard is [public](dashboards.md#public-dashboards): it opens without signing in, and
then shows only what anyone may see. Nicks, IPs and MACs never reach the screen, and the plan draws
the public marks only (Overview and Safety, like the attendee pages), since a big screen is often in
a public place. Change it in **Dashboards** like any other dashboard, for example to add a text with
the Wi-Fi name, or make your own.

## Options

| Address | What it shows |
|---------|---------------|
| `/kiosk` | The Kiosk dashboard (`/dashboards/kiosk`). |
| `/kiosk?hall=<id>` | The same, on another hall than the first ([halls.md](halls.md)). |
| `/kiosk?theme=<preset>` | The same, in another theme preset, remembered by the browser ([themes.md](themes.md)). The default is `kiosk`. |
| `/kiosk?view=heat` | The floor plan full screen with each seat coloured by its traffic right now (`/plan?screen=1&layers=marks,status`). Needs an account. |

The old page's other options (`title`, `refresh`, `labels`, `grid`, `marks`, `reload`) are gone:
the title is the event name, switch status comes with the live updates, and the dashboard reloads
itself after a Floorbit update. Set a plan pane's **Plan marks** to **None** for no marks.

## On the screen

- Chromium in kiosk mode (`chromium --kiosk https://floor.example.com/kiosk`) shows it full screen.
- The mouse pointer hides after 3 seconds, and a clock sits in the corner.
- Someone at the screen can drag and zoom the plan; it goes back after a minute.

## Other big screens

The [health wall](health.md) (`/health?screen=1`), the [stats dashboard](stats.md)
(`/stats?screen=1`) and the floor plan (`/plan?screen=1`) have big-screen versions too, with the same
kiosk theme and no personal data. They need an account: sign the screen in with a `kiosk` account.

## Rotating views with a seat finder

`/screen` shows one view at a time and moves on every `every` seconds, with a QR code in the
corner that opens the seat finder on a phone. Sign the screen in with a `kiosk` account.

| Option  | Default            | What it does |
|---------|--------------------|--------------|
| `views` | `floor,heat,stats` | Which views, in order: `floor` (the Kiosk dashboard), `heat` (the plan with seat traffic, `/plan?screen=1&layers=marks,status`), `stats` (`/stats?screen=1`), `health` (`/health?screen=1`). |
| `every` | `30`               | Seconds per view (10 to 600). |
| `qr`    | `1`                | `0` hides the QR code. |
| `theme` |                    | Theme preset for every view ([themes.md](themes.md)). |
| `hall`  | the first hall     | Which hall `floor` and `heat` show. |

Each view stays loaded after its first turn, so it keeps its live updates, and the next one loads
before it fades in. Moving the mouse shows the cursor and the view's name, with buttons to go back and
on; the arrow keys do the same. `GET /api/screen` with the same options answers what the screen shows.
The QR code points at `PUBLIC_URL/find`, so set `PUBLIC_URL`
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

The attendee view (`/hall`, a public hall plan with every seat online or offline) is gone: it showed
when a seat's player was away. `/hall` now leads to the [network status page](status-page.md), which
tells attendees what they need during an outage: which halls, blocks and rows are hit.
