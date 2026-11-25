# Halls and floor plan import

An event can have more than one hall or floor. Each has its own floor plan: a background image,
switches and seat blocks. The floor plan shows one hall at a time.

## Halls

The hall picker above the plan switches between halls (the address gets `?hall=<id>`; editing
stays editing). While editing, **Plan ▾ → Halls…** in the top bar opens the Halls dialog:

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
(seat mapping, stats, incidents, power) works the same with more than one hall.

## Background image

A PNG, JPEG, WebP or SVG of the hall plan, up to 5 MB, or a PDF: the browser turns its first page
into an image (on white, 3200 pixels on the longest side) before it is sent. It is drawn under the
switches and seats in the editor and on the kiosk, first stretched to the plan area. Images are kept
next to `data.json` in a `halls/` folder, and backups carry them, with where they sit.

### Placing it and setting the scale

While editing, with nothing selected, the panel has **Background**:

- **See-through** fades the drawing so the seats stand out.
- **Move and resize** puts a frame round it: drag inside to move it, the corner to scale it (it keeps
  its shape). **Done** ends it, **Fill the plan** puts it back on the whole plan area. Each change is a
  step to undo.

The **scale** says how many metres one seat (one grid cell) is. With the Measure tool (M), draw a
line over something whose length you know, give its real length, and:

- **Set the scale from this line** when the seats already match the drawing: from then on walls, zones
  and the Measure tool show metres next to seats.
- **Fit the background to the seats** once there is a scale: the drawing is scaled round the line's
  start so the line gets its real length.

Templates and plan versions carry the image, where it sits and the scale.

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
| `cols`, `rows` | yes | Seats per row and rows: a rectangle. Rows of their own (lengths, shapes) are set in the editor afterwards. |
| `rotation` | no | Degrees, 0 by default. |
| `seat_width`, `seat_height`, `spacing_x`, `spacing_y` | no | Kept for older files; every block draws its seats at the same size. |
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
**Seat 1 on the right** runs the numbers the other way.

**Defaults:** every block draws its seats at the same size and spacing. What a new block starts with (seat
names, where the row letter goes, seat 1 on the left or right, and the room between blocks made at once) is
set under Settings > Floor plan (`FLOORPLAN_NAMING`, `FLOORPLAN_ROW_LABELS`, `FLOORPLAN_REVERSE_NUMBERS`,
`FLOORPLAN_BLOCK_GAP`); the New seat block dialog keeps the rest under **More options**, and a block's details
can still change it later.

**Add several blocks at once:** in the New seat block dialog, set **How many blocks**, whether the next one
goes below or to the right, and the gap. The row letters (or single-letter block names) count on, so 4 blocks
of 2 rows from `E` are rows E to L. A seat name is never given twice, in any hall: a block that would repeat
one is refused with the seat it clashes on. `POST /api/seat-blocks/many` does the same for scripts
(`count`, `dx`, `dy` in percent of the plan, plus the block's fields).

## Rows in a seat block

A seat block is a run of rows that are placed, turned and named together. **Add block** makes the usual run:
two rows back to back with a one-seat spacer between them for the switch (**Spacer between rows**; 0 for
rows that touch). A block can hold one row or many; for a whole hall, add several runs at once and group
them. The edit panel has a tab for each part of a block:
**Block** (name, rotation, mirror and flip, duplicate, lock, delete), **Rows**, **Seats** (seat names,
seats placed freely, where seat 1 is) and **Items** (everything on the plan). The panel is 440 pixels wide
(520 on screens 1600 pixels wide and more); drag its left edge to make it wider or narrower, and
double-click the edge to go back. Floorbit remembers the width in this browser.

In **Rows**, each row of the block has a small tab, top row first; double-clicking a row on the plan opens
its tab. The picked row shows the space above it and its fields:

- **+** puts a row under the others, as long as the last one. The arrows move a row earlier or later and
  **×** takes it out. With a letter per row the letters follow the order, so moving row D above row C
  makes it C.
- **Spacers** are the room between two rows, for a switch. They have no label: a small hatched cue
  between two row tabs, and a hatched band between the rows on the plan while you edit (empty space on the
  live plan). **Spacer above …** under the tabs adds one to the picked row (one seat); its size field and
  **×** change or remove it (0 to 20 seats). Drop a switch into a spacer like anywhere else on the plan.
- **On the plan**, the selected block shows a bar or spacer between each two rows. Drag it up or down to
  change the space above the lower row, in quarter seats (hold Alt, or turn snapping off, to place it
  freely). The rows above stay where they are; the rows below move. Clicking it picks the row under it.
- **Seats and gaps**, at the top of the picked row's fields, shows the row's seats in a line. Click between
  two seats to add a gap there (one seat, for a fiber roll or a post); click a gap to size or remove it.
  Seat numbers carry on across a gap, and gaps show hatched on the plan while you edit.
- **Mirror block** turns the whole block over left to right where it stands: every row, their line-up
  and shift, and seats placed freely. **Flip block** turns it upside down (mirrored and turned half
  round, so it shows 180° under Rotation); like any turned block it then numbers from where a reader
  starts.
- **Double-click a row** on the plan to select its block and pick that row in the panel. The picked row
  is outlined on the plan.
- Pick a row to change it on its own:
  - **Seats per row**: rows in a block can differ, for a block that narrows towards a pillar or the stage.
  - **Shape**: **Straight**; **Arc** (how far the row turns from its first seat to its last, in degrees,
    negative for the other way); **U** round a table (you set the seats on the first and the last side; the
    middle takes the rest of the row); **L** (two arms); **Path** (seats follow points; it starts as an L). Seats stand one seat
    apart along the shape and turn with it.
  - **Line up with the other rows**: at the start, the middle or the end of the widest row, plus a
    **Shift** in seats.
  - **Chairs**: people sit left or right of the way the row runs, drawn as a small grey square outside
    each seat on that side (hidden when zoomed far out). "Shape default" draws nothing on a straight row
    and the inside of an arc, U or L. **Set chairs automatically** on the Block tab sets them for every
    straight row ([cables.md](cables.md#where-seat-cables-plug-in)).
  - **Cables connect** (straight rows): where the row's seat cables plug in, Auto, behind the table or on
    the chair side ([cables.md](cables.md#where-seat-cables-plug-in)).
  - **Mirror** turns the row over left to right, **Flip** upside down: an L that turns the other way,
    a U that opens downwards. The seats keep their numbers and the people stay on the same side of the
    shape; the shape's handles work as before.
  - **Pieces** (Path): a path row can be in up to 8 pieces, each its own tab with a colour on the plan.
    The seats run through the first piece, then each later one in turn, so the row keeps one run of
    numbers: a U of 34 seats with a straight piece of 10 inside it is still row Z, seats 1 to 44. A
    later piece has its own seat count; the first piece takes the rest and keeps at least one seat.
  - **Row letter** (with a letter per row): as the block says, beside seat 1, after the last seat, both
    or hidden. Drag the letter on the plan to put it anywhere; it then moves with its row.
  - **Number this row the other way**, and **gaps in this row**: an empty space after a seat, for a
    fiber roll or a post (0.25 to 20 seats). Seat names and numbers carry on across a gap.
- **A picked row's shape has handles on the plan**, and faint seats show where they will go while you drag:
  - **Arc**: drag the round handle on the middle seat to bend the row through that point (5° steps).
  - **U** and **L**: drag the square handle past an arm's end to make the arm longer or shorter; the
    middle (U) or the other arm (L) gives or takes the seats, so the row keeps its count.
  - **Path**: drag a point to move it (quarter seats), click a **+** halfway along a line to add a point
    (up to 50), and Alt-click or double-click a point to remove it (a path keeps two). Each piece has its
    own points.
  - **Row letter**: drag the dashed circle round the picked row's letter (half seats).
  - Hold Alt, or turn snapping off, to place freely. The block stays where it is: a U's middle, an L's
    corner or the row's first seat keeps its place (the last seat when the path's first point moves).

Every change is one step to undo. The Seats view, the kiosk, dashboards and the port dispatch draw what the
server lays out, so they show the rows' shapes too.

Each row has an id inside its block that stays when rows are reordered: circuits, seat walks and
dashboards that pick a row keep the same row. Blocks saved before rows existed (a number of columns and
rows, gaps for the whole block) are moved to rows once when Floorbit starts, with ids 1, 2, 3 in their old
order, so what named a row by its place still names the same row. Old templates and backups are read the
same way.

**In the API** a block has `rows`, top first, each
`{"id", "seats", "shape", "gap", "align", "shift", "side", "reverse", "col_gaps", "mirror", "flip"}` and optional `cables` (`behind` or `chair`; Auto when left out) plus `bend` (arc), `sides`
(U and L) or `path` (`[[x, y], ...]` in seats) with optional `pieces` (`[{"path", "seats"}]`, the
pieces after the first), and optional `label` (`start`, `end`, `both`, `hidden` or `moved` with
`label_at`, a point in the row's own frame). A new block can still be given as `cols` and `rows` numbers
(a rectangle, as the Block tool and the CSV import make it). Rules: `floorbit/seat_rows.py`.

## Alignment guides, groups and merging

**Alignment guides:** while you drag a seat block (or a selection of blocks), it snaps when its edges,
its middle or its rows of seats line up with another block, and a red line shows which. Between two
blocks, it also snaps where the space on both sides is the same, and shows that space in seats. The guides
win over the grid on the axis they snap. Hold <kbd>Alt</kbd> while dragging to place freely.

**Snapping and rulers:** the four buttons right of **Layers** show the grid, snap to the grid, snap to other
items (the guides above) and show the rulers; a green button is on. The rulers mark where the pointer is,
in seats from the plan's corner, and while you drag, the middle of what moves.

**Groups** keep several blocks together while you lay out the hall. Select the blocks (<kbd>Shift</kbd>+click
or a box with <kbd>Shift</kbd>+drag) and press <kbd>Ctrl</kbd>+<kbd>G</kbd>, or use **Group** in the selection
panel or the right-click menu. From then on a click on any of them selects the whole group (a dashed frame
shows it), and the group moves, turns (<kbd>R</kbd>, <kbd>Shift</kbd>+<kbd>R</kbd>) and copies
(<kbd>Ctrl</kbd>+<kbd>D</kbd>) as one. Each block keeps its own seat names. <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>G</kbd>
or **Ungroup** splits it again. <kbd>Ctrl</kbd>+click (<kbd>Cmd</kbd> on a Mac) picks one item out of its group, so you
can drag it on its own; the group stays.

**Merge** (in the panel when you have selected two or more seat blocks and nothing else) makes one block
of blocks next to each other, as if it had been made that size:

- Blocks **stacked** become one block with more rows, whatever the rows are like; the space between them
  becomes the space above the first joined row. With a letter per row, the rows keep their letters (E, F,
  then G).
- Blocks **side by side** with as many straight rows and the same space between them become one wider
  block, and the seat numbers carry on (A-1 to A-12, then A-13 to A-18). The space between them becomes a
  gap in each row.

The blocks have to be turned the same way, use the same kind of seat names and stand in line. The top or
left block keeps its name and settings, so the other blocks' seats get new names. Undo brings the separate blocks back. For scripts: `POST /api/seat-blocks/merge` with
`{"ids": [...]}`; a block's `group` is a free text id.

**Split** goes the other way. Pick a row other than the first on the block's **Rows** tab and click
**Split block above row …**: that row and the rows after it become a new block, in the same place and
turned the same way. With a letter per row every row keeps its letter, so no seat changes its name. A block
with a name keeps it for the top part, and the new block gets the next free name (A gives B, Gaming gives
Gaming 2), with its seats numbered from 1. A block with seats placed by hand needs **Back to rows** first.
Undo joins the block again. For scripts: `POST /api/seat-blocks/<id>/split` with `{"at": 2}`, the place in
the block of the first row that moves, counted from 0.

## What is drawn on top

Switches are always drawn over seat blocks, seats, labels, walls and zones, as a small switch box (lit ports
when it is online, a cross when it is offline, a dashed outline when its status is unknown). That is the same in
the editor, on the Seats view and on the kiosk.

Seat blocks overlap in the order you set: right-click a block (or a selection of blocks) or a label, wall,
zone or icon and pick **Bring to front**, **Bring forward**, **Send backward** or **Send to back**, or press
<kbd>Ctrl</kbd>+<kbd>]</kbd> / <kbd>Ctrl</kbd>+<kbd>[</kbd> (with <kbd>Shift</kbd>: all the way). Blocks are
ordered among blocks and marks among marks; marks always stay under the blocks. Every view draws in the same
order. In the API it is `z` on a block or mark (a whole number, higher on top, 0 by default).

## The editor's menu

The **tool rail** on the left holds the tools (Select <kbd>V</kbd>, Switch <kbd>S</kbd>, Seat block
<kbd>B</kbd>, Draw <kbd>D</kbd>, Cable <kbd>C</kbd>), the buttons for the three panels, and at the bottom
Undo, Redo, Snap to grid <kbd>G</kbd> and the keyboard shortcuts <kbd>?</kbd>.

A tool stays on after you place something, so several switches, blocks, icons, walls or zones go down in
a row; <kbd>Esc</kbd> or <kbd>V</kbd> goes back to Select. Only a text label goes straight back to Select,
with its text ready to type.

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

**Walkways** (the **Walkway** tool, <kbd>K</kbd>) are the aisles between seat blocks. Draw one like a wall,
from one end to the other, and set its **width** in seats (2 when new). It shows as a pale band with a
dashed middle line on the Overview and Safety layers. With snapping on, a seat block dragged next to a
walkway snaps with its seats right on the band's edge, so the walkway's width is the space between the
blocks on either side. There is no separate gap item between blocks: draw a walkway instead. On the API a
walkway is a mark with `kind: "walkway"`, `x`/`y` to `x2`/`y2`, optional `points` and `width` (0.5 to 20).

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
| Firewall per seat | Seats on a fallback firewall, or with none up (needs firewall ranges) |
| Wi-Fi | Access points placed on this hall, their rough coverage, coloured by load (counts only) |
| Safety | Marks on the safety layer: exits, extinguishers, escape routes, the assembly point, and every walkway |
| Crew | Open incidents per seat and per switch |
| Check-in | The check-in corner on seats |
| Services | Marks on the services layer: server racks, LANcache, DNS |

**Presets** set several at once: *Overview*, *Network*, *Electrical* and *Ops* (network, traffic, firewalls,
incidents, check-in). The choice is part of the address (`?layers=marks,network,wifi&fade=wifi:60`), so a
bookmark or a big screen (`&screen=1`) shows the same. Old links with `?traffic=1`, `?power=1` or
`?firewalls=1` still work. A layer that isn't set up is listed but can't be switched on.

Safety and services are marks: in the editor, pick the **Layer** of a label, wall, zone or icon. New
extinguisher, escape route and assembly point icons land on Safety, a server on Services, a router or access
point on Network, a power or socket icon on Electrical.

In the editor, the **Layers** panel on the right (<kbd>L</kbd>) has the same five mark layers (Overview, Safety, Network,
Electrical, Services). Switching one off hides its marks while you edit, so a busy plan can be worked on one
layer at a time; the editor remembers this per browser. A new mark on a hidden layer switches that layer back
on. **Open these layers on the Seats view** opens this hall there with the same mark layers and check-in.

## Saved views

**Saved views ▾** in the plan's top bar keeps what the plan shows now under a name: where it looks and its
zoom, the layers and how strong they are, and the seat filter. Pick a view from the same menu to open it
again; the menu lists the views of the hall shown. **Copy link to this view** gives an address with
`?pv=<id>` that opens the view (hall, layers, filter and position). **Update** saves the current state into
the open view, **Delete** removes it.

Views are shared with the event's crew; **Only for me** keeps one personal. Saving, updating and deleting
need `floorplan.edit`; everyone who sees the plan can open the shared ones. Views belong to the event
(`plan-views.json`), like its halls. API: `GET/POST /api/plan-views`, `PUT/DELETE /api/plan-views/<id>`.

## Big screens and attendee pages

- `/kiosk?hall=<id>` (or `/dashboards/<id>?hall=<id>`) shows another hall than the first; with `?rotate=` it goes along to
  every dashboard in turn. With more than one hall, the kiosk heading names the hall.

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
