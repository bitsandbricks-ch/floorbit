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

Any [dashboard](dashboards.md) works on a big screen at `/dashboards/<id>`, with the same kiosk
look and clock. Floorbit comes with ready-made ones for the NOC (Service health, Network, Services,
Traffic, Power load) and the public **Event in numbers**. Those that are not public need an account:
sign the screen in with a `kiosk` account. The floor plan alone is `/plan?screen=1`.

## Rotating dashboards

`?rotate=<id>,<id>,...&every=<seconds>` on a dashboard's address moves on to the next one every so
many seconds (10 to 600, 30 by default), for example
`/dashboards/kiosk?rotate=kiosk,traffic,event&every=45`. `hall` and `theme` go along.

## Attendee view

The attendee view (`/hall`, a public hall plan with every seat online or offline) is gone: it showed
when a seat's player was away. `/hall` now leads to the [network status page](status-page.md), which
tells attendees what they need during an outage: which halls, blocks and rows are hit.
