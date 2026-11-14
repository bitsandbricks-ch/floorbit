# Seats view

**Seats** (`/plan`, the **Seats** button in the floor plan editor) shows every seat of a hall with
one state, drawn the same way everywhere. It is for reading the hall during the event; seat blocks
are still placed and changed in the floor plan editor (`/`).

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
- **Middle:** seat states and their marks.
- **Near** (a seat 30 px or more): seat numbers and switch names too.

**Show** dims every seat except the ones with problems, offline seats, seats that changed lately,
match seats or checked-in seats. **Find a seat** takes `D-6`, `d6` or `D-06` and zooms to it.

## Keyboard and screen readers

Tab to the plan, then:

| Key | Does |
| --- | --- |
| Arrow keys | Move a dashed cursor to the next seat in that direction, in rotated blocks too. The first press starts on the open seat or the one in the middle of the view. The view follows the cursor. |
| Enter or Space | Open the seat under the cursor in the inspector. |
| Escape | Close the inspector. |
| B | Open the block of the seat under the cursor. |
| Shift + arrow keys | Move the map. |
| **+**, **-**, **0** | Zoom in, out, or show the whole hall. |

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

## List

**Map / List** switches the plan for a table of the hall's seats: seat, state, problems, traffic,
check-in and match zone. Click a column to sort (problems and traffic start with the most), and the
**Show** filter applies here too, so "every offline seat" is two clicks. Click a seat to open the
inspector. **CSV** downloads what the list shows. `/plan?view=list` opens the page as a list; it is
also the plain way through the hall for screen readers and small phones.

## The inspector

Clicking a seat opens one panel with everything about it: state, block, switch and port, traffic
now, check-in, match zone, open incidents and needs-attention items, and links to the seat in the
editor and to the incidents. On a phone it opens from the bottom.

**Link** shows the seat's port over the last 6 hours: a full green bar while it was up, a thin red
one while it was down, and nothing before Floorbit's first read. Below it: since when the seat is
online or offline and how often the link changed. It is built from the changes Floorbit already
keeps for the [replay](replay.md), so it needs nothing new. When a player says "my internet keeps
dropping", this answers whether the port did.

Techs can act from the panel too, with the same rules as the editor:

- **Bounce port** (needs `ports.act` and a port actions plugin, see [Port actions](ports.md)):
  asks for the tech's own switch login when the plugin needs one, never stores it, and asks again
  for a match seat.
- **Flag for a tech** (needs `incidents.work`): opens a "Tech visit" incident at the seat with a
  note, like the editor's flag.

Who sits there (nick, IP and MAC) is only shown to accounts with `seats.view` (techs, leads and
admins). Everyone with `floorplan.view` sees the states. The link `/plan?seat=D-6` opens the page
on that seat.

## The block panel

Click a block's name (or its totals when zoomed out), click **Block** in the seat inspector, or press
**B** on a seat to open the block instead of a seat: online, offline and unknown seats with a bar,
check-ins, traffic in total, the switches that serve the block with how many of their seats are
online, and the seats with problems (click one to open it). When half a block goes dark, it shows
at a glance whether it is one switch. `/plan?block=D` opens it. It shows states only, never who
sits where.

## The switch panel

Click a switch's marker, or a switch's name in the block panel, to see that switch: its status and
since when, and the seats it serves port by port with their states (click one to open it). Before
walking to a switch, you see which players it takes down. `/plan?switch=sw-c-02` opens it.

## In the floor plan editor

The editor draws seats with the same shapes through the **Seat states** layer (on by default,
under Layers), with a short legend and a link to the Seats view. The traffic heatmap takes over
the seat colours while it is on.

## Big screens

`/plan?screen=1` is the plan without the header, for a kiosk or the ops room, with the legend and
the totals. It reloads every 30 seconds and with each port read.

With more than one hall, add `cycle` to rotate through them: `/plan?screen=1&cycle=30` shows each
hall for 30 seconds (10 at least), with its name on top and a bar that fills until the next one. A
hall with seats with problems stays up twice as long. Add `&traffic=1` to rotate the traffic overlay.
