# Dashboards

A dashboard is a set of widgets on a grid, saved under a name. Put one on the TV at the ops desk, a
wall in the hall, or your own second monitor. Widgets can be grouped in named sections, and a widget
can be split into panes side by side or stacked. Each pane shows one thing:

| Pane | What it shows |
| --- | --- |
| **Plan** | A hall's floor plan: the whole hall, one seat block, a zone you drew on the plan, or a view you zoomed to. With a layer preset (Overview, Network, Electrical, Ops), a seat filter, how seats are numbered and which plan marks it draws. |
| **Widget** | A rich widget (a chart, a map, a table) from the widget list (`frontend/src/widgets/views.ts`). |
| **Tile** | One dashboard tile: Floorbit's own (problems, incidents, switches, seats, switches down) or a plugin's. |
| **Tiles** | A saved tile layout from the [tile dashboard](dashboard.md). |
| **Page** | Service health, stats, the public stats wall or the status page. |
| **Text** | Your own words: a welcome, the schedule, the Wi-Fi name. A small Markdown (`# heading`, `- list`, `**bold**`, `[link](https://example.com)`); every line stays its own line. Four sizes (S to XL) that grow with the pane, aligned left or centred. |

For example: the whole hall on the left, the VIP zone zoomed in at the top right, and the network
layer at the bottom right.

## Making one

**Dashboards** in the sidebar lists them; **New dashboard** opens the editor (needs
`floorplan.edit`, like the tile layouts):

- **Add widget** puts an empty widget in the first free spot of the picked section. Drag a widget by
  its handle (top left) and resize it by its corner (bottom right); the others make room and
  everything floats up, on a grid of 24 columns. With the keyboard: focus the handle, then the arrow
  keys move it and Shift with the arrow keys resizes it. Up to 24 widgets.
- **Add section** starts a named section below the others. A section's title is optional: without
  one it is just a divider line. Sections fold (the arrow before the title), move up and down, and
  can be removed with their widgets. Folding on a screen is only for whoever looks at it; folding
  in the editor is saved.
- **Fit to screen** stretches the rows so the whole dashboard fills the screen, for a wall. Without
  it, rows have a fixed height and the page scrolls, like a dashboard on your own monitor.
- Click a pane to set it up in the panel on the right.
- **Split right** and **Split down** cut a pane in two; drag the border between two panes to resize
  them. Up to 40 panes on a dashboard, splits up to four deep.
- **Plan** panes show their hall's name and area as a title, and how many of the seats in that area
  are online or have problems. A title you type replaces it.
- **Hide the title** leaves a pane's head off, for a cleaner wall (on a plan pane, the online count
  goes with it).
- **Zone** lists the zones of the hall that have a label: draw one around the VIP area with the
  editor's Zone tool first. **My view** shows a small plan: move and zoom it, then **Use this view**.
- **Plan marks** on a plan pane: **All** draws the marks of its layers, **Public** only the Overview
  and Safety marks (as the [attendee pages](kiosk.md#attendee-view) do), for a screen people walk
  past, and **None** none.
- **Public** lets the dashboard open without signing in (below).
- **Rotate halls every** makes plan panes without a fixed hall that show a whole hall go through all
  halls in turn.

## Kiosk

**Kiosk** is a ready-made dashboard for the big screen in the hall, and what `/kiosk` opens: the
first hall's plan with the public marks only, and beside it how many switches are up, how many
seats are online, and which switches are down and for how long. It is public. Change it like any
other; saving keeps your version under the same name, and deleting your version brings the
ready-made one back. See [kiosk.md](kiosk.md).

## Public dashboards

A dashboard with **Public** on opens without signing in, for a screen in the hall or a link on the
event website. Signed out, it shows only what anyone may see:

- **Plan** panes: seats online or offline, taken or checked in and their traffic, switches by name
  and status, and the public marks only (a pane set to **All** draws the public ones). No nicks,
  IPs, MACs, notes, seat problems, power boards or patch panels, and no power, firewall, Wi-Fi or
  crew layer.
- **Tiles**: Floorbit's switches, seats online and switches down tiles.
- **Text** and empty panes.

Any other pane (other tiles, widgets, tile layouts, pages) says it needs an account. Someone signed
in sees the whole dashboard as usual. For a screen that should show more, sign it in with a `kiosk`
account or a custom role ([auth.md](auth.md)).

A signed-out screen reads `GET /api/dashboards/<id>/public` and, below it, `/plan?hall=` and
`/tiles/<tile>`; they answer only for a public dashboard and only for what it shows.

## On the screen

**Open full screen** opens `/dashboards/<id>`: no sidebar, a clock in the corner, the pointer hides
after three seconds, and the page reloads itself after a Floorbit update. Saved changes reach the
screen within a minute. Someone at the screen can drag and zoom a plan pane; it goes back to its
area after a minute. On a phone the panes are stacked.

Seat numbers follow the zoom ([zoom levels](seats.md#zoom-levels)); set a plan pane's
**Seat numbers** to **Always** or **Never** to override that.

`?hall=<id>` on the screen's address shows that hall on the plan panes without a hall of their own,
for example `/dashboards/kiosk?hall=hall-2`. `?theme=<preset>` picks the look, as on every page
([themes.md](themes.md)); the Kiosk dashboard uses the `kiosk` preset unless the site theme says
otherwise.

## For developers

Data: `floorbit/dashboards.py` (data.json key `dashboards`), API `GET/PUT/DELETE /api/dashboards/<id>`.
A dashboard is `sections` (each with an optional `title`, `folded` and its `panels`), and a panel is
`x`, `y`, `w`, `h` on the 24-column grid plus a `node` (a pane or a split of panes). Layouts saved
as one split tree (`root`) are read as one panel filling the screen. How panels make room is in
`frontend/src/pages/dashboards/grid.ts`.
A rich widget is a React component registered with one line in `frontend/src/widgets/views.ts`; it
gets `expanded` and has no page or route of its own. Floorbit's own tiles are one line in
`TILES` (`floorbit/dashboard_core.py`) plus their builder in `CORE_TILES`
(`floorbit/blueprints/plugins.py`). What a public dashboard may show is `PUBLIC_TILES` and
`public_board()` in `floorbit/dashboards.py`.
