# Dashboards

Floorbit's dashboards share one kind of card for their figures: Stats, Wi-Fi and Problems show a
label, the number, a line under it, and where it helps a colour edge (green fine, amber to look at,
red down) and a small trend line over the last hour. Cards and list entries that point at a place
drill down to it on the [Seats page](seats.md), in the hall it is in: an uplink or a busy switch
opens `/plan?switch=<name>`, a busy seat `/plan?seat=<seat>`. The traffic, logs and brackets pages
link seats the same way. On a big screen (`?screen=1`) the links are left out.

## The dashboard and saved layouts

`/dashboard` shows Floorbit's own tiles and the tiles of the plugins that are on (see
[Plugins](plugins.md)). Floorbit's own come first and need no plugin:

- **Problems right now:** how many things are down, with what is left to look at, port trouble and
  what is muted underneath. It links to the [Problems page](alerts.md).
- **Incidents:** how many are open, how many have waited 10 minutes or more with nobody on them, and
  how many are being worked. It links to the [incident board](incidents.md). Only people who see the
  board get this tile.
- **Switches:** how many placed switches are up, of how many, with offline and not known under it.
  Red while one is offline.
- **Seats online:** how many seats are online, of how many, from the last port read. It shows **?**
  when there has been no read lately, rather than an old number.

Their texts follow the browser's language. In a layout they are `floorbit/w/problems`,
`floorbit/w/incidents`, `floorbit/w/switches` and `floorbit/w/seats`; no plugin may use the id `floorbit`. By default the dashboard
shows every tile this account may see. A **layout** picks some of them, in an order, in 1 to 4
columns, for one screen: the ops desk might show DHCP and the uplink in two columns, the NOC wall
everything.

- Pick a layout from the list at the top; the address becomes `/dashboard?layout=<id>`.
- **Full screen** opens `/dashboard?layout=<id>&screen=1`, without the header, for a kiosk.
- **New layout** and **Edit layout** (needs `floorplan.edit`): tick the tiles, move them up and
  down, name the layout and pick the columns. **Delete layout** removes it.

A tile whose plugin is off, or that the viewer's role may not see, is left out of the layout
without an error. Layouts are kept in `data.json` under `dashboard_layouts` (at most 30) and the
changes are in the audit log.

## API

| Route | What |
| --- | --- |
| `GET /api/dashboard` | the tiles this account may see |
| `GET /api/dashboard/floorbit/<problems, incidents, switches or seats>` | one of Floorbit's own tiles, as a widget |
| `GET /api/dashboard/layouts` | the saved layouts |
| `PUT /api/dashboard/layouts/<id>` | `{"name": "Ops desk", "tiles": ["unifi/w/clients"], "columns": 2}`; a tile is `<plugin>/<w or a>/<id>` (widget or action) |
| `DELETE /api/dashboard/layouts/<id>` | removes a layout |
