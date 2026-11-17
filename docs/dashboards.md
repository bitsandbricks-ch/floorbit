# Dashboards

A dashboard is a screen split into panes, saved under a name. Put one on the TV at the ops desk, a
wall in the hall, or your own second monitor. Each pane shows one thing:

| Pane | What it shows |
| --- | --- |
| **Plan** | A hall's floor plan: the whole hall, one seat block, a zone you drew on the plan, or a view you zoomed to. With a layer preset (Overview, Network, Electrical, Ops), a seat filter and how seats are numbered. |
| **Widget** | A rich widget (a chart, a map, a table) from the widget list (`frontend/src/widgets/views.ts`). |
| **Tile** | One dashboard tile: Floorbit's own (problems, incidents, switches, seats) or a plugin's. |
| **Tiles** | A saved tile layout from the [tile dashboard](dashboard.md). |
| **Page** | Service health, stats, the public stats wall or the status page. |

For example: the whole hall on the left, the VIP zone zoomed in at the top right, and the network
layer at the bottom right.

## Making one

**Dashboards** in the sidebar lists them; **New dashboard** opens the editor (needs
`floorplan.edit`, like the tile layouts):

- Click a pane to set it up in the panel on the right.
- **Split right** and **Split down** cut a pane in two; drag the border between two panes to resize
  them. Up to 12 panes, splits up to four deep.
- **Plan** panes show their hall's name and area as a title, and how many of the seats in that area
  are online or have problems. A title you type replaces it.
- **Zone** lists the zones of the hall that have a label: draw one around the VIP area with the
  editor's Zone tool first. **My view** shows a small plan: move and zoom it, then **Use this view**.
- **Rotate halls every** makes plan panes without a fixed hall that show a whole hall go through all
  halls in turn.

## On the screen

**Open full screen** opens `/dashboards/<id>`: no sidebar, a clock in the corner, the pointer hides
after three seconds, and the page reloads itself after a Floorbit update. Saved changes reach the
screen within a minute. Someone at the screen can drag and zoom a plan pane; it goes back to its
area after a minute. On a phone the panes are stacked.

Seat numbers follow the zoom ([zoom levels](seats.md#zoom-levels)); set a plan pane's
**Seat numbers** to **Always** or **Never** to override that.

## For developers

Data: `floorbit/dashboards.py` (data.json key `dashboards`), API `GET/PUT/DELETE /api/dashboards/<id>`.
A rich widget is a React component registered with one line in `frontend/src/widgets/views.ts`; it
gets `expanded` and has no page or route of its own.
