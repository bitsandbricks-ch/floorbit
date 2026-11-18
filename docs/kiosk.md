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

## Rotating views

`/screen` shows one view at a time and moves on every `every` seconds. Sign the screen in with a
`kiosk` account.

| Option  | Default            | What it does |
|---------|--------------------|--------------|
| `views` | `floor,heat,stats` | Which views, in order: `floor` (the Kiosk dashboard), `heat` (the plan with seat traffic, `/plan?screen=1&layers=marks,status`), `stats` (`/stats?screen=1`), `health` (`/health?screen=1`). |
| `every` | `30`               | Seconds per view (10 to 600). |
| `theme` |                    | Theme preset for every view ([themes.md](themes.md)). |
| `hall`  | the first hall     | Which hall `floor` and `heat` show. |

Each view stays loaded after its first turn, so it keeps its live updates, and the next one loads
before it fades in. Moving the mouse shows the cursor and the view's name, with buttons to go back and
on; the arrow keys do the same. `GET /api/screen` with the same options answers what the screen shows.

## Attendee view

`/hall` shows the hall plan with every seat green when it is online (its switch port is up) and grey
when it is not, plus "312 of 400 seats online". It needs no account, so it can go on the event website
or a screen at the entrance, and it works on phones in English and German.

It shows seat numbers and online or offline, nothing else: no nicks, addresses, MACs, switches or ports.
It is **off by default**, because it also shows when a seat is empty, for example while its player is
away. Switch it on under **Settings > Attendee pages** (or `ATTENDEE_VIEW=true`).

- The status comes from the same port reads as the stats page (every `ATTENTION_INTERVAL`, 120 s),
  so no extra requests go to the switches.
- The page reloads the hall and its status every minute from `GET /api/public/hall` (`?hall=<id>`).
  For the event website, `GET /api/public/seats` gives the status alone
  (`{"seats": {"D-6": true, ...}, "online": 1, "total": 8, "updated": <unix time>}`).
- After three missed reads the page says the status isn't available instead of showing old dots, and
  the API answers `null` for every seat.
