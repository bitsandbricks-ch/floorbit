# Demo mode

Demo mode fills Floorbit with a made-up LAN, so you can try it without a network. The pull
request screenshots use it too, so they show a filled-in floor plan.

## Turning it on

- Set `FLOORBIT_DEMO=1`, or
- turn on **Demo data** under **Settings > Plugins**.

While it's on, every page shows a **Demo data** badge at the bottom. With `FLOORBIT_DEMO=1` it
stays on and can't be turned off on the Plugins page.

## What you get

The built-in `demo` plugin (`floorbit/builtin_plugins/demo/`) feeds every data area:

- **Inventory:** 15 devices:
  - a core router
  - two distribution switches
  - three access switches for each of the seat blocks A to D
- **Seat mapping:** a player on most of the 96 seats, with:
  - nicks like `player-07`
  - IPs from `192.0.2.0/24`
  - locally administered MACs (`02:00:...`)
- **Live data:** this replaces LibreNMS while the demo is on.
  - Status, CPU, memory and temperature for each switch.
  - Port details with traffic that moves slowly.
  - A few heavy downloaders.
  - One seat on half duplex, one with CRC errors.
  - `sw-c-02` goes down for one minute in every four, so you can see alerts and the status monitor work.

The data is computed from the clock, so it needs no state and looks the same on every instance.
Nothing in it is real: example names, documentation IP ranges (RFC 5737), no real people.

## The floor plan

With `FLOORBIT_DEMO=1`, the demo hall is laid out once at start-up: switches placed and four seat
blocks drawn. This only happens if the floor plan is still empty, so it never moves anything
someone placed. When you turn the demo on from the Plugins page instead, `POST /api/demo/layout`
(admins) does the same.

Your own switches, seat blocks and hand entries stay as they are. To go back, turn the plugin off,
or unset `FLOORBIT_DEMO`. The demo devices stay in the inventory, marked as fed by the demo, until
you delete them.
