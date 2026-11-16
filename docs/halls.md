# Halls and floor plan import

An event can have more than one hall or floor. Each has its own floor plan: a background image,
switches and seat blocks. The editor shows one hall at a time.

## Halls

The hall picker in the editor's top bar switches between halls (the address gets `?hall=<id>`, and
the browser remembers the last one). The button next to it opens **Halls**:

- **Add hall**, rename one by editing its name.
- **Delete** a hall once it is empty: move or delete its switches and seat blocks first. The last
  hall always stays.
- **Background image** for each hall (below).
- **Import seat blocks (CSV)** into a hall (below).
- **Templates** opens the [template library](templates.md): save a hall or the whole plan, start from one.

An install from before halls is one hall called "Hall", holding everything. Nothing changes until
you add a second one.

A switch is placed in the hall shown when you place it; unplaced switches show in every hall's list.
Block names stay unique across halls, so seat numbers do too, and everything that works with seats
(seat mapping, stats, incidents, power, the seat finder) works the same with more than one hall.

## Background image

A PNG, JPEG, WebP or SVG of the hall plan, up to 5 MB, drawn faded under the switches and seats in
the editor and on the kiosk. It is stretched to the plan area, so an image with the hall's aspect ratio
lines up best; place a few seat blocks over it and adjust. Images are kept next to `data.json` in a
`halls/` folder, and backups carry them.

An uploaded SVG is served so it can't run script when opened on its own.

## Seat blocks from a CSV file

A header row, then one seat block per line, comma or semicolon separated:

```csv
name,x,y,cols,rows,rotation
A,20,25,12,2,0
B,60,25,12,2,0
C,20,60,12,2,90
```

| Column | Required | Meaning |
| --- | --- | --- |
| `name` | yes | The block's name; seat numbers are `<name>-<n>`. Unique across every hall. |
| `x`, `y` | yes | The block's centre, in percent of the plan box (0 to 100 is the box the background image fills; the plan has no edge, so values outside it work too). A decimal comma works. |
| `cols`, `rows` | yes | Seats per row and rows. |
| `rotation` | no | Degrees, 0 by default. |
| `seat_width`, `seat_height`, `spacing_x`, `spacing_y` | no | Sizes in percent of the plan, as in the editor. |
| `reverse_numbers` | no | `true` to number right to left. |
| `naming` | no | `block` (default: `<name>-1` to `<name>-<n>`) or `rows` (a letter per row, see below). |
| `row_start`, `row_labels` | no | With `rows`: the first row's letter (`A`), and where the letter is drawn: `start`, `end`, `both` or `none`. |

The import is all or nothing: if a line is wrong (a missing column, a number out of range, a name used
twice or already on the plan), nothing is added and the editor lists the lines to fix. At most 500 blocks
per file.

## Seat names: a letter per row

A seat block names its seats in one of two ways:

- **A letter per row** (`naming: rows`, the default for new blocks): every row of the block is a hall row with
  its own letter, counted on from the first row, and its seats are numbered from 1. A block of 2 rows from
  `E` has `E-1` to `E-20` and `F-1` to `F-20`. The letter is drawn before seat 1, after the last seat, on both
  ends or not at all. The block's name is only a label above it.
- **Block name and a number** (`naming: block`, how older blocks stay): `A-1` to `A-24` over all its rows.

Turning a block (the Rotation buttons, or <kbd>R</kbd> and <kbd>Shift</kbd>+<kbd>R</kbd> on the floor plan)
turns the numbering with it: seat 1 and the first row letter stay where a reader starts, left and top as seen.
**Reverse numbering** runs the numbers the other way.

**Add several blocks at once:** in the New seat block dialog, set **How many blocks**, whether the next one
goes below or to the right, and the gap. The row letters (or single-letter block names) count on, so 4 blocks
of 2 rows from `E` are rows E to L. A seat name is never given twice, in any hall: a block that would repeat
one is refused with the seat it clashes on. `POST /api/seat-blocks/many` does the same for scripts
(`count`, `dx`, `dy` in percent of the plan, plus the block's fields).

## Gaps in a seat block

A row can have room in it, for example where the fiber rolls stand, and two rows can have a lane between
them for a switch. Both are set per block:

- **In the rows:** an empty space after a column, in every row of the block. Right-click a seat and pick
  **Gap after this seat (every row)**, or use **+ Gap** in the block's **Gaps** section in the inspector.
- **Between rows:** an empty lane after a row. Right-click a seat and pick **Lane after this row**, or use
  **+ Lane**. Drop a switch into the lane like anywhere else on the plan.

Each gap has a size in seats (0.25 to 20; a new gap is 1 seat wide, a new lane 2 seats high). Columns and
rows are counted from the top left of the block as drawn before it is turned. Gaps only move seats apart:
seat names and numbers carry on across them, and the Seats view, the kiosk and the port dispatch use the
same spacing. Undo works as usual. In the API a block has `col_gaps` and `row_gaps`, each a list of
`{"after": n, "size": s}`; gaps after the last column or row are dropped when a block gets smaller.

## The editor's menu

The **tool rail** on the left holds the tools (Select <kbd>V</kbd>, Switch <kbd>S</kbd>, Seat block
<kbd>B</kbd>, Draw <kbd>D</kbd>), the buttons for the three panels, and at the bottom Undo, Redo, Snap
to grid <kbd>G</kbd> and the keyboard shortcuts <kbd>?</kbd>.

The **panel on the right** shows **Search** (<kbd>/</kbd>), **Layers** (<kbd>L</kbd>) or **Switches**
(<kbd>W</kbd>, with the NetBox sync when NetBox is set up). Pressing the button of the open panel again
closes it, so the plan gets the whole width. Selecting a switch, seat, block or mark opens its inspector
in the same place; closing it (<kbd>Esc</kbd>) brings the panel back. A status chip in the top bar filters
the switch list and opens it. The editor remembers the open panel per browser.

## Labels, walls, zones and icons

Besides seats, the floor plan holds marks: **text** labels, **walls** (solid or dashed, for fences),
**zones** (a tinted area with a name, such as the bar or the crew corner) and **icons** (exit, WC, bar,
food, first aid, stage, stairs, Wi-Fi, arrows and more). Add them with **Draw** in the editor's tool rail
(<kbd>D</kbd>): text and icons take one click, walls and zones two (start and end corner). Select a mark to
change its text, size, colour, rotation or style, drag it to move it, <kbd>Delete</kbd> removes it. Marks
show on the Seats view, the big screens and the attendee hall view as well. `GET /api/plan-marks?hall=<id>`
lists them with the icon shapes; `POST`, `PUT` and `DELETE /api/plan-marks/<id>` change them (editors).

**Example hall:** *Add an example hall* in the Halls dialog (`POST /api/halls/example`) creates a new hall
with 8 pairs of 2×24 rows, a standing row turned on its side, outer walls with an entrance, a fenced side
events area, bar and crew zones and a few icons. Its rows count on from the last row letter in use, so it
never clashes with seats you have. To remove it, delete its seat blocks, then the hall; its marks go with it.

## Layers on the Seats view

The Seats view (`/plan`) stacks layers over the seats. **Layers** above the map switches each one on or off
and sets how strong it is drawn; the seats themselves are always there.

| Layer | Shows |
| --- | --- |
| Grid | The editor's grid, so things sit on the same lines as in the editor. Presets leave it as it is |
| Labels, walls and zones | The marks on the overview layer |
| Network | Switches, uplinks with their type and speed, network marks |
| Electrical | Distribution boards, power cables per circuit, electrical marks (needs Power) |
| Status | Each online seat filled by its traffic |
| Firewall per seat | Seats failed over to a backup firewall, or with none up (needs firewall ranges) |
| Wi-Fi | Access points placed on this hall, their rough coverage, coloured by load (counts only) |
| Safety | Marks on the safety layer: exits, extinguishers, escape routes, the assembly point |
| Crew | Open incidents per seat and per switch |
| Check-in | The check-in corner on seats |
| Services | Marks on the services layer: server racks, LANcache, DNS |

**Presets** set several at once: *Overview*, *Network*, *Electrical* and *Ops* (network, traffic, firewalls,
incidents, check-in). The choice is part of the address (`?layers=marks,network,wifi&fade=wifi:60`), so a
bookmark or a big screen (`&screen=1`) shows the same. Old links with `?traffic=1`, `?power=1` or
`?firewalls=1` still work. A layer that isn't set up is listed but can't be switched on.

Safety and services are marks: in the editor, pick the **Layer** of a label, wall, zone or icon. New
extinguisher, escape route and assembly point icons land on Safety, a server on Services, a router or access
point on Network, a power or socket icon on Electrical. Attendee pages (`/hall`, `/find`) show the Overview
and Safety marks only.

In the editor, the **Layers** panel on the right (<kbd>L</kbd>) has the same five mark layers (Overview, Safety, Network,
Electrical, Services). Switching one off hides its marks while you edit, so a busy plan can be worked on one
layer at a time; the editor remembers this per browser. A new mark on a hidden layer switches that layer back
on. **Open these layers on the Seats view** opens this hall there with the same mark layers and check-in.

## Big screens and attendee pages

- `/kiosk?hall=<id>` shows another hall than the first; `/screen?hall=<id>` passes it on to its
  floor plan views. With more than one hall, the kiosk heading names the hall.
- The seat finder (`/find`) draws the hall the seat is in and names it.
- The attendee view (`/hall`) has a tab per hall.

## API

| Method and path | Needs | What |
| --- | --- | --- |
| `GET /api/halls` | `floorplan.view` | The halls in order: id, name, background URL, how many switches and seat blocks. |
| `POST /api/halls` `{"name"}` | `floorplan.edit` | Add a hall. |
| `PUT /api/halls/<id>` `{"name"}` | `floorplan.edit` | Rename. |
| `DELETE /api/halls/<id>` | `floorplan.edit` | Delete an empty hall (409 otherwise). |
| `GET /api/halls/<id>/background` | `floorplan.view` | The image. |
| `PUT /api/halls/<id>/background` `{"image": "data:image/png;base64,..."}` | `floorplan.edit` | Set it. |
| `DELETE /api/halls/<id>/background` | `floorplan.edit` | Remove it. |
| `POST /api/halls/<id>/seat-blocks.csv` | `floorplan.edit` | The CSV as `text/csv`, or `{"csv": "..."}`. 400 with `errors: [{line, error}]` if anything is wrong. |

`GET /api/switches` and `GET /api/seat-blocks` take `?hall=<id>`, and every switch and seat block
has a `hall_id`. `POST` and `PUT` on them take `hall_id` (the first hall when left out).
