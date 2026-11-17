# Floor plan

The **Floor plan** (`/plan`) shows every seat of a hall with one state, drawn the same way
everywhere, and its Edit mode is where the plan is built. `/` opens it too; old links with
`?hall=`, `?seat=` or `?switch=` open it in Edit mode for crew who may edit.

## Modes

The plan fills the whole page next to the sidebar, like a map editor. One slim bar on top holds the
hall, the mode, the online count, the filters (each with its count), Map/List, **Layers**, the find
box, **Print** and **?** (help and keys). The plan takes everything below it, with a panel docked on
the right, as in a map editor. Its tabs are **Layers** (the layer switches), **Problems** (switches
that are down, seats with problems, seats offline) and **Items** (every block and switch); click a row
to open it. An open seat, block or switch takes the panel's place, and closing it (or **Esc**) brings
the tabs back. The panel button in the top bar, or **]**, hides the panel for more plan; the panel
remembers whether it was open and which tab. On a phone the open item shows below the plan instead,
and Layers stays in the top bar. Each layer's key sits under its switch in **Layers**: what the
seats' shapes mean under the seats line, the power colours under Electrical, the traffic scale under
Status, the cable colours and dashes under Network (in Network mode), and so on. While Layers isn't in
view (another tab, an open item, the panel hidden), the same key floats over the plan's bottom-left
corner: click **Legend** to fold it away.

The bar switches between modes of the same plan, kept in the address (`?mode=`):

| Mode | What it shows |
| --- | --- |
| **Live** | Seats with their state, the network, traffic, the crew's incidents and check-ins. |
| **Check-in** | Labels and check-ins only, filtered to the seats that checked in (only when check-in is on). |
| **Network** | Switches and uplinks, traffic, firewalls and Wi-Fi. |
| **Edit** | The editor, for crew who may edit the plan (`floorplan.edit`): see below. |

The TV button (**Kiosk**) opens the same plan full screen for a big screen (`?screen=1`), with the hall and layers
you were looking at.

The older editor stays at `/editor/classic` for a while as a fallback, linked from the bottom of
Edit mode's panel. Everything it did is in Edit mode.

### Edit mode

The floor plan editor is moving into this page. Edit mode already does:

- **Select:** click an item (seat block, switch, label, icon, wall, zone); Shift-click adds or
  removes; dragging on empty plan selects everything inside the box; Ctrl+A selects all.
  Ctrl+Shift+A (or **Select all like this** in the right-click menu) selects everything like the
  selection: all seat blocks, all switches, or with a wall selected all walls (text, icons and
  zones the same way).
- **Move:** drag, or the arrow keys (Shift for five steps). Items land on the editor's 0.5 % grid;
  hold Alt while dragging to place freely.
- **Move the view:** the **Hand** tool (H, under Select) drags the view; Space + drag or the middle
  mouse button do the same with any tool. Esc or V goes back to Select.
- **Change:** in the panel on the right: a block's name, rotation, seats per row and rows; a label's
  text, size and rotation; an icon's size and rotation; a zone's label and colour; a wall's style;
  which layer a mark is on.
- **Resize:** select one label, icon, zone or wall and drag its handles: a label's or icon's corner
  makes it any size (shown in %, picking Small, Medium or Large again undoes the stretch), a zone's
  corners resize the box, a wall's ends move. Handles snap to the grid unless you hold Alt.
- **Copy and paste:** Ctrl+C, Ctrl+X and Ctrl+V. Paste puts the copy where the pointer is; Ctrl+D
  duplicates one seat further on. Copied seat blocks get the next free row letter (or block name),
  so no seat exists twice. The clipboard survives a reload.
- **Order:** Ctrl+] brings the selection to the front, Ctrl+[ sends it to the back.
- **Selection buttons:** with something selected, the panel on the right has buttons for what the
  right-click menu does: duplicate, turn, bring to front, send to back and zoom to the selection.
- **Turn:** R turns the selected seat blocks, labels and icons a quarter turn each, Shift+R turns
  them back (also "Turn 90°" in the right-click menu). One undo puts them all back.
- **Zoom to the selection:** F brings the view in on what is selected (also in the right-click menu,
  or double-click an item in the items list); 0 shows the whole hall again.
- **Groups:** Ctrl+G puts the selected items in a group (seat blocks, labels, icons, walls, zones,
  switches, patch panels, boards; cables follow their ends), Ctrl+Shift+G takes them out. A click on
  one item of a group picks the whole group; Shift-click takes the group out of the selection.
- **Keyboard only:** with an item selected, Tab and Shift+Tab step to the next and previous item (top to bottom, left to right), and the view follows; Esc lets Tab leave the plan. Screen readers hear what is selected. The items list in the panel works with the keyboard too.
- **Keys:** press ? (or "All keys" in the panel) for every Edit mode key, by tool, selection, moving and changing.
- **Items list:** the panel on the right lists everything on the hall's plan, the groups first. Click
  an item or a group to select it (Shift adds), search by name, double-click a group to rename it, or
  take it apart with its unlink button. Groups travel in backups; layout templates leave them out.
- **Arrange:** with several items selected, the panel lines them up (left, centre, right, top,
  middle, bottom edges) or spreads three or more with the same gap.
- **Guides:** while dragging, the selection snaps to another item's edge or middle when it comes
  within a few pixels, and a dashed line shows which; otherwise it lands on the grid (Alt: neither).
- **Right click** an item (or empty plan) for the same actions in a menu.
- **Delete** (Del) seat blocks and marks; switches stay (remove them in the editor).
- **Undo and redo:** Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y, also for deletes. The clock button next to them
  lists the last steps: click one to go back to before it, or a grey (undone) one to redo up to it.

The tools down the left (each stays on after placing something; Esc or V goes back to Select):

| Tool | Key | How |
| --- | --- | --- |
| Select | V | As above. |
| Seat block | B | Click where it goes; the dialog takes the defaults from **Settings › Floor plan** and the next free row letter. Several blocks at once go down or to the right with the gap from Settings. |
| Switch | S | Click where it goes: tick switches from the inventory that aren't on a plan yet (several land in a small grid) or make one by hand. Del takes a switch off the plan; one from the inventory stays there, unplaced. |
| Label | T | Click, type the text, pick the size. |
| Icon | I | Click, search the icon (exit, toilets, bar …), pick the size. |
| Wall | W | Drag from one end to the other. It shows the length in seats and the angle; Shift keeps 15° steps. |
| Zone | Z | Drag a box; it shows its size in seats. The new zone is selected so you can name it. |
| Patch panel | P | Click where it hangs; give its name (the next free one is filled in) and how many ports it has (12, 24, 48 or up to 96). Selected, it shows which seat is on each port. |
| Cable | C | Click a seat, a switch or a patch panel: the cable form opens with it filled in (a seat the switches already see on a port starts with that port). Switch port and panel port list only free ports. |
| Distribution board | E | Click where the power board hangs; give its name (the next free one is filled in) and where it is. Selected, it lists its circuits with their load and adds new ones; Shift-click seat blocks or switches with it and **Feed** puts them on one of its circuits. Ratings, phases and meters stay on the Electrics page. Shown only when Electrics is on. |

Everything lands on the grid unless you hold Alt.

A selected seat block shows its name, rotation, seats per row and rows, how its seats are named
(a letter per row or the block's name), the first row letter and where the row letters go, whether
seat 1 is on the right, and its gaps: room in every row after a column, or a lane after a row.
Seat numbers carry on across a gap.

Seat cables are drawn on the Network layer in Edit and Network mode; dashed ones are only read from
the switches, not recorded yet. In Network mode the legend explains the colours (copper,
fiber, DAC), widths (speed) and dashes for the cables on that plan, and counts the links between switches
and how many are down or slow. A link that is down gets a red ✕ in its middle, the same size at every zoom. Click one to select it, Del removes it, **Change cable** opens its
form. A selected cable shows its bends: drag one to move it, drag the dot in the middle of a
stretch to add one, double-click a bend to remove it (Alt places it off the grid). The panel sets
square or round corners and puts a drawn cable back on its automatic route. Every change is
saved at once and can be undone.

## What a seat shows

Each state has its own shape as well as its own colour, so the plan reads in grey scale, in every
theme and for colour-blind eyes:

| Seat | Means |
| --- | --- |
| Filled green | **Online:** its switch port was up in the latest port read. |
| Hollow with a red slash | **Offline:** its port is known and down. |
| Dashed outline | **Unknown:** there is no recent port read, or Floorbit doesn't know its port yet. |
| Cyan corner | **Checked in** (only with [seat check-in](integrations.md#seat-check-in-page) on). |
| Red "!" | An open incident at the seat, or port trouble from the needs-attention list. |
| Amber frame | A **match seat**: the seat is in a [match zone](tournament.md). |

A port read counts as recent for three needs-attention intervals (`ATTENTION_INTERVAL`, 2 minutes
by default). After that every seat is unknown and the page says so, rather than showing seats as
offline that might be fine.

## Zoom levels

Drag to move, scroll or pinch to zoom; **+**, **-**, **0** and **Shift** with the arrow keys work
when the plan has focus (see [Keyboard and screen readers](#keyboard-and-screen-readers)). What is drawn depends on how big a seat is on screen:

- **Far** (a seat under 12 px): each block's name with its online and total seats and its
  problems.
- **Middle:** seat states and their marks, and next to each block's name how many of its seats have
  problems ("C ! 7"). Seat numbers stay as long as they can be read: from about 18 px a seat, every
  seat keeps its number, written smaller to fit; below that, only the first and last seat of each row
  keep theirs, so you can count from the end of the row. Row letters grow to stay readable.
- **Near** (a seat 30 px or more): seat numbers at full size and switch names too.

The status colours and shapes are the same at every level, so a 600-seat hall zoomed all the way
out on a big screen still shows where the trouble is.

Zoomed in so that part of the hall is off screen, a small overview of the hall shows in the bottom
left corner: the seat blocks (red where a block has many problems) and a frame for the part on
screen. Click or drag on it to move there. It shows in Edit mode too.

A block where a quarter of its seats or more have problems (two at least) gets a red outline at
every zoom level. That many at once usually has one cause, such as the block's switch or its power.

**Show** dims every seat except the ones with problems, offline seats, seats that changed lately,
match seats, seats with a note or checked-in seats. Each choice shows how many seats it matches in
this hall, so "Offline 0" answers the question without a click. The **with problems** count above
the plan is a shortcut: click it to show only those seats, and again to show all. The choice is kept in the address
(`/plan?show=offline`), so a reload or a link sent to another tech keeps it, and switching halls does too. **Find a seat** takes `D-6`, `d6` or `D-06` and zooms to it.

With more than one hall, the hall picker shows each hall's seats online and seats with problems,
and the header says how many seats have problems in the other halls, so trouble there shows before
you switch. The browser tab counts them too: "(3) Seats · Floorbit" means three seats with
problems in all halls, so a tab in the background still shows when something needs a look. A link with a seat or switch but no hall (`/plan?seat=E-3`) opens the hall that seat or
switch is in.

## Keyboard and screen readers

Tab to the plan, then:

| Key | Does |
| --- | --- |
| Arrow keys | Move a dashed cursor to the next seat in that direction, in rotated blocks too. The first press starts on the open seat or the one in the middle of the view. The view follows the cursor. |
| Enter or Space | Open the seat under the cursor in the inspector. |
| Escape | Close the open seat, block or switch panel (from anywhere on the page; in the search box, Esc clears it). |
| B | Open the block of the seat under the cursor. |
| **1** to **4** | Anywhere on the page: switch the layers to a preset, Overview, Network, Electrical or Ops, as in the **Layers** panel. Not in Edit mode or the list. |
| L | Anywhere on the page: switch between the map and the list, like the **Map**/**List** switch. Not in Edit mode. |
| Shift + arrow keys | Move the map. |
| **+**, **-**, **0** | Zoom in, out, or show the whole hall. |
| **/** | Anywhere on the page: put the cursor in **Find**, with the last search selected. Works where **/** needs Shift, such as Shift+7 on Swiss and German keyboards. The box shows a **/** hint on computers with a mouse. |
| **]** | Hide or show the panel on the right. Not in Edit mode. |
| **?** | Anywhere on the page: list these shortcuts. The **?** button at the end of the top bar opens the same list. |

A screen reader reads each seat as the cursor reaches it ("D-2: Offline · 1 problem") and, with the
plan's description, one line per block ("Block D: 21 of 24 seats online, 1 problem."). The page is
checked with axe in the frontend tests.

## Traffic

**Traffic** fills each online seat by its traffic now, on a fixed scale from 100 kbit/s to
1 Gbit/s (log scale, so the same colour means the same traffic in every hall and at every hour).
The colours run from dark purple to yellow (viridis), which stay in order for colour-blind eyes
and in grey scale. Offline and unknown seats keep their shapes. Only each seat's volume is shown,
never what it is. `/plan?traffic=1` opens with it on, also on big screens.

## Changed lately

A seat whose link went up or down in the last 15 minutes gets a dashed cyan ring that pulses (it
stays still for people who turned motion off), and its label says "changed 4 min ago". **Show >
Changed lately** keeps only those seats, on the map and in the list, so "what just went down?" is
one click during an outage. Floorbit's first port read after a start doesn't count as a change.

## Finding a seat or a player

The search box takes a seat number (`d6`, `D 6` and `D-06` all find D-6). It also takes the name
of a seat block or a switch in this hall (`C`, `sw-c-01`, or the start of a switch name when only
one switch has it): the plan moves there and opens the block's or the switch's panel. Accounts with `seats.view`
can also type a nick, an IP or a MAC: one match opens that seat, switching hall if needed, and
several show a short list to pick from. It is the same search as the seat mapping's
([Finding a player](seat-mapping.md#finding-a-player)). Everyone else searches by seat number only, and the plan
itself never carries names.

## List

**Map / List** switches the plan for a table of the hall's seats: seat, state, problems, traffic,
check-in, match zone and whether the crew left a note. Click a column to sort (problems, traffic and
notes start with the most), and the
**Show** filter applies here too, so "every offline seat" is two clicks. Click a seat to open the
inspector. **CSV** downloads what the list shows. `/plan?view=list` opens the page as a list; it is
also the plain way through the hall for screen readers and small phones.

## The inspector

Clicking a seat opens one panel with everything about it: state, block, switch and port, traffic
now, check-in, match zone, open incidents and needs-attention items, how often an incident was
fixed at the seat before (with the latest one), and links to the seat in the editor and to its
incidents (the board filtered to the seat, `/incidents?q=seat:D-6`). A seat that keeps breaking usually has a cable or port
to swap. On a phone it opens from the bottom.
While a seat is open, its switch gets a ring on the plan and a dashed line leads from the seat to it
(with the network layer on and the switch placed in this hall), so you know where to walk.

**Copy link** puts the page's address with this seat open on the clipboard (hall, filter and view
included), to paste into the crew chat. It holds the seat number only, nothing about the player.

**Link** shows the seat's port over the last 6 hours: a full green bar while it was up, a thin red
one while it was down, and nothing before Floorbit's first read. Below it: since when the seat is
online or offline and how often the link changed. It is built from the changes Floorbit already
keeps for the [replay](replay.md), so it needs nothing new. When a player says "my internet keeps
dropping", this answers whether the port did.
**Speed tests** (needs `incidents.work`): the last three tests the player ran from the seat's
[help page](speedtest.md), with down, up and ping. A test from before the link last changed is
marked, so a slow result from before a cable swap isn't read as slow now.
**Watch this seat** sends a browser notification when the seat's link changes (see
[Notifications](notifications.md#watching-a-seat)).

Techs can act from the panel too, with the same rules as the editor:

- **Bounce port** (needs `ports.act` and a port actions plugin, see [Port actions](ports.md)):
  asks for the tech's own switch login when the plugin needs one, never stores it, and asks again
  for a match seat.
- **Flag for a tech** (needs `incidents.work`): opens a "Tech visit" incident at the seat with a
  note, like the editor's flag.

**Crew note** (needs `incidents.work`): one short note per seat, up to 500 characters, such as
"cable swapped at 14:20" or "brought their own switch, leave it", so the next tech at the seat
knows what was done. The panel shows who wrote it and when; anyone with `incidents.work` can edit or
remove it, and each change goes to the audit log. Everyone else only sees that the seat has one: a
small amber corner on the map and the **Has a note** filter. Starting a new event (on the report)
clears the notes.

Who sits there (nick, IP and MAC) is only shown to accounts with `seats.view` (techs, leads and
admins). Everyone with `floorplan.view` sees the states. The link `/plan?seat=D-6` opens the page
on that seat.

## The block panel

Click a block's name (or its totals when zoomed out), click **Block** in the seat inspector, or press
**B** on a seat to open the block instead of a seat: online, offline and unknown seats with a bar,
check-ins, traffic in total, the switches that serve the block with how many of their seats are
online, and the seats with problems (click one to open it). When half a block goes dark, it shows
at a glance whether it is one switch. While it is open, the plan dims the other blocks' seats.
`/plan?block=D` opens it. It shows states only, never who
sits where.

## The switch panel

Click a switch's marker, or a switch's name in the block panel, to see that switch: its status and
since when, and the seats it serves port by port with their states (click one to open it). Before
walking to a switch, you see which players it takes down. `/plan?switch=sw-c-02` opens it.
While the panel is open, the plan dims every seat the switch doesn't serve and puts a ring around
the switch, so its seats stand out even across several blocks.

## In the floor plan editor

The editor draws seats with the same shapes through the **Seat states** layer (on by default,
under Layers), with a short legend and a link to the Seats view. The traffic heatmap takes over
the seat colours while it is on.

## Printing

**Print** opens `/plan?print=1`: the whole hall fitted to the page with every seat numbered, the
legend, the hall's name and the port read's time, light on white whatever the theme. The filter
carries over (`&show=offline` prints only the offline seats). Use the browser's print dialog for
paper size; landscape is the default. The sheet has no names, IPs or notes, so it can lie on a
table at the info desk.

**Save as image** on the same sheet downloads the plan as a picture, for a chat or a briefing
slide: PNG (twice the screen's width) or SVG (sharp at any size). It shows what the sheet shows,
light on white, with the hall's background picture if it has one.

## Big screens

`/plan?screen=1` is the plan without the header, for a kiosk or the ops room, with the legend and
the totals. It reloads every 30 seconds and with each port read.
When Floorbit stops answering (the network or the server is down), a red "Not updated since …"
badge appears next to the totals, on the big screen and in Live mode, so nobody takes old seat
states for live ones. It goes away by itself with the next answer.
In the top right corner the big screen shows the time, the blocks with problems (most first, up to
six, e.g. "D: 2 seats"), and how many seats have problems in the other halls, so the crew sees where
to go from across the room. While it rotates through the halls, the other halls come up anyway, so
that last line is left out.
After three seconds without use, the mouse pointer and the zoom buttons hide, so they don't sit
on top of the plan; moving the mouse brings them back.
The big screen asks every five minutes which version of Floorbit runs, and loads the page again
after an update, so a screen left on for the whole event doesn't keep running the old version.

With more than one hall, add `cycle` to rotate through them: `/plan?screen=1&cycle=30` shows each
hall for 30 seconds (10 at least), with its name on top and a bar that fills until the next one. A
hall with seats with problems stays up twice as long. Add `&traffic=1` to rotate the traffic overlay.
