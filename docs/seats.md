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

Drag to move, scroll or pinch to zoom; **+**, **-**, **0** and the arrow keys work when the plan has
focus. What is drawn depends on how big a seat is on screen:

- **Far** (a seat under 12 px): each block's name with its online and total seats and its
  problems.
- **Middle:** seat states and their marks.
- **Near** (a seat 30 px or more): seat numbers and switch names too.

**Show** dims every seat except the ones with problems, offline seats, match seats or checked-in
seats. **Find a seat** takes `D-6`, `d6` or `D-06` and zooms to it.

## Traffic

**Traffic** fills each online seat by its traffic now, on a fixed scale from 100 kbit/s to
1 Gbit/s (log scale, so the same colour means the same traffic in every hall and at every hour).
The colours run from dark purple to yellow (viridis), which stay in order for colour-blind eyes
and in grey scale. Offline and unknown seats keep their shapes. Only each seat's volume is shown,
never what it is. `/plan?traffic=1` opens with it on, also on big screens.

## The inspector

Clicking a seat opens one panel with everything about it: state, block, switch and port, traffic
now, check-in, match zone, open incidents and needs-attention items, and links to the seat in the
editor and to the incidents. On a phone it opens from the bottom.

Techs can act from the panel too, with the same rules as the editor:

- **Bounce port** (needs `ports.act` and a port actions plugin, see [Port actions](ports.md)):
  asks for the tech's own switch login when the plugin needs one, never stores it, and asks again
  for a match seat.
- **Flag for a tech** (needs `incidents.work`): opens a "Tech visit" incident at the seat with a
  note, like the editor's flag.

Who sits there (nick, IP and MAC) is only shown to accounts with `seats.view` (techs, leads and
admins). Everyone with `floorplan.view` sees the states. The link `/plan?seat=D-6` opens the page
on that seat.

## In the floor plan editor

The editor draws seats with the same shapes through the **Seat states** layer (on by default,
under Layers), with a short legend and a link to the Seats view. The traffic heatmap takes over
the seat colours while it is on.

## Big screens

`/plan?screen=1` is the plan without the header, for a kiosk or the ops room, with the legend and
the totals. It reloads every 30 seconds and with each port read.
