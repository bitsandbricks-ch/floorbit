# Cables and patching

`/cables` (Settings > Cables) records which switch port goes to which patch panel port and seat,
and prints a label for both ends of each cable. Issue #97.

The page has three tabs (issue #880), kept in the address: **Cables**, the list, where each cable
opens its own page; **Check** (`?tab=check`), the cables against the network and the machines on
the seat ports; and **Port areas** (`?tab=areas`).

A cable is **switch port → patch panel port → seat**. The panel and the seat are optional: a seat
patched straight into the switch has no panel, and an uplink has no seat.

| Field | |
| --- | --- |
| Switch, switch port | Needed. One cable per switch port: a second one is almost always a typo. |
| Patch panel, panel port | Optional. A panel port needs its panel. A panel placed on the plan has a port count (24 unless set, up to 96): its ports are 1 to that, and each takes one cable. |
| Seat | Optional, written in capitals (`A-12`). |
| Label | Printed on both ends. Left empty, Floorbit numbers the cables `C-0001`, `C-0002`, ... Labels are unique. |
| Colour, length, note | Optional. The length is 0.1 to 500 metres. |
| Type, speed | Optional: copper Cat5e/6/6a, fiber single-mode or multi-mode, or DAC, and 1, 10, 25, 40 or 100G, as for the [links between switches](topology.md). |

Nothing that Floorbit already knows is typed in: the switch, its port, the patch panel, its port and
the seat are picked from lists. Ports list only the free ones (and keep the cable's own); tick
**Also list ports that have a cable** to see the rest, with the seat on each.

Each cable has its own page, `/cables/<id>`: the list links to it, its label's QR code opens it, and
it's where the cable is changed, printed or deleted. **Add cable** opens `/cables/new`, which can
take `switch`, `port`, `panel`, `panel_port` and `seat` from the address to start filled in. The
floor plan's Edit mode still edits a cable in a dialog, so the plan stays in view.

## A whole block at once

**Patch a block** makes a cable for every seat of a seat block, so a hall is a few dozen of these
instead of thousands of cables typed one by one (issue #473). Say once:

- the **seat block** and the **switch** it is patched to,
- the **port of the first seat** (`Gi1/0/1`); the last number counts up, keeping leading zeros (`Eth1/09`, `Eth1/10`),
- the **order**: along each row the same way, or **snake** (every other row back),
- whether to **start at the last seat**, and which **rows** (`1-2`; all when empty). A block on
  two switches is two plans, one per range of rows.

The preview shows which seat gets which port, and every cable already in the way: on one of those
ports, or on one of those seats. Nothing is made until you press **Make**, and then all or none.
Cables in the way stop it unless you tick **Replace the cables in the way**; ones from NetBox always
stop it (change them in NetBox). Planning the same block and rows again (shifted by a port, another
switch) moves that block's own cables without asking. Each plan is written to the audit log.

## Seats on the floor plan and in the logs

A cable to a seat is how Floorbit knows which port is that seat: port problems name the seat, and
syslog lines from that port are tied to it. Where no cable says so, the port's description on the
switch (`Seat A-12`) still does. A cable wins over the description: it is what the crew patched.

## Against the network

Once switches are up, the **Check** tab checks the plan against what LibreNMS says about the ports
(the port watch's last read, so it asks LibreNMS nothing extra):

- per block, how many seat ports are **up**;
- cables that name a **port the switch doesn't have**: a typo, or the wrong switch;
- **port descriptions naming another seat** than the cable does;
- **ports up that no cable explains**, on switches that have seats: a seat outside the plan, or a
  device the crew didn't note. An uplink shows here until it has a cable (one without a seat says
  what it is);
- seat ports **not up yet** (normal before doors), and switches that weren't read.

## Machines on the seat ports

The port check says which ports are up; **Machines on the seat ports** says what is on them. It reads
the MAC table of every switch that has seats (LibreNMS FDB, through the agent on a hosted Floorbit)
and the ARP table for the seats' networks, and lists:

- **machines on another seat's port**: the port is cabled to A-2, but the machine on it has A-3's IP
  (from the seat mapping). Players swapped seats, or two cables are swapped at the switch;
- **machines on a port no cable explains**, with their MAC and IP, and the seat that IP belongs to.
  **Patch to a seat** opens a new cable's page with the port and that seat filled in; **Infrastructure**
  adds a cable without a seat (a crew laptop, an access point), so the port isn't asked about again;
- **seat ports with more than one machine**: the seat, the port and how many machines, never which.
  Two or three are usually a console next to the PC. More than 4 is marked **Switch or router at the
  seat**: that is where loops, a home router handing out addresses and a seat the mapping can't place
  start. Both also show under [Seats with trouble](alerts.md#seats-with-trouble) in Problems, one line per
  seat, or one line for all of them when there are more than 5;
- **IPs in the seat networks on no seat port** (issue #949): ARP knows the IP, but no seat switch's
  edge port carries its MAC: a PC behind a desk switch, or on a switch Floorbit doesn't read. The
  gateway (the .1) and the inventory's own boxes are left out, and the list only shows after a read
  where every seat switch answered;
- **seats cabled to a port with no machine**: only once check-ins have started, so it isn't every
  seat before the doors open.

**Ignore** takes a MAC off these lists for good (a printer, a crew PC); `GET /api/cables/clients/ignored`
lists them and `DELETE` puts one back. That needs `floorplan.edit`, like **Infrastructure**.

Other ports with more than 4 MACs are uplinks, and ports cabled without a seat are
infrastructure: neither is listed. Floorbit reads every five minutes in the background while a
monitoring source is set up, and opening the page asks for a read too, at most every two minutes
(LibreNMS itself refreshes MAC tables only when it polls, so this adds no load on the switches).
A switch that doesn't answer is named. This list names MACs and IPs, so it needs `seats.view`.

## Walking the row

**Walk the row** (`/cables/walk`, on a phone) finds each seat's port by plugging in: pick the block, its
switch and the order, then go seat by seat with a laptop. The page shows the switch port that just came
up; **That's A-5** puts the seat on it:

- the seat's cable moves to that port, or a new one is made;
- a cable without a seat on that port (infrastructure) is taken over;
- when the plan gives that port to another seat, the page asks first, and **Swap** trades the two
  seats' ports.

**Not this one** skips a port (a neighbour plugging in), **Skip seat** goes on. When the row reaches
the next switch, change the switch on the page.

With the syslog receiver on (`SYSLOG_ENABLED`, or relayed by the local agent) a port shows within
seconds: Floorbit reads the switch's link-up lines (Cisco `changed state to up`, MikroTik `link up`,
Juniper `LINK_UP`, Aruba `is now on-line`). Without it, the page compares LibreNMS' port list with
the ports that were up when the walk began, which only changes when LibreNMS polls the switch.

## Rough port areas

Often nobody knows each seat's port before the event, but the crew knows the layout in batches: a
40-port access switch serves its row, ports 1-10 to A-1..A-10, 11-20 to A-11..A-20, and so on.
The **Port areas** tab takes exactly that: a switch, ports per batch (10), the first port
number, and the first seat of each batch. Each batch goes to as many seats from there as it has
ports; leave a batch empty for uplinks or access points. Saving replaces that switch's areas.

An area never says which port a seat is on: a cable, or a port learned from a seat check-in, always
wins. What an area does:

- **Walking the row** says when the port that came up lies in another seat range than the seat you
  stand at.
- **Machines on the seat ports** shows the area next to each unexplained client, so you know which
  part of the row to walk to.
- **Seat check-in** puts a learned port outside its area on the review list (kind `area`, also on
  Problems): usually a wrong PIN or a seat card on the wrong desk.
- The crew's **Check-in** page shows the area of each found port.

A port's number is the last number in its name (`Gi1/0/14` is 14). Areas live in `data.json` with
the plan, so a backup carries them.

## Labels

**Print labels** makes an A4 PDF of 3 × 8 labels, two per cable: the switch end first, then the far
end (the seat, or the panel when there is no seat). Each label has:

- the cable's label, large;
- the end it goes on (`sw-a-01 Gi1/0/3` or `Seat A-3`), in bold;
- where the other end goes, small, and the colour, length, type and speed;
- a QR code that opens the cable's own page (`/cables/<id>`).

The PDF holds the cables the search shows. A cable's own window prints just its two labels. Behind a
reverse proxy, set `PUBLIC_URL` so the QR codes point at the address phones reach.

## From NetBox

When the NetBox plugin is set up, **More › Import cables** (it names the sources below it) reads `/api/dcim/cables/` and adds every
cable with a switch interface on one end:

- the interface's device and name become the switch and switch port;
- a front or rear port on the other end becomes the patch panel and panel port;
- the seat comes from the cable's description, written as `Seat: A-12` (NetBox has no seats);
- the cable's label, colour and length come along. A cable without a label is `NB-<NetBox id>`.

Each import replaces the last one, so NetBox stays the place to change these cables: they can't be
edited in Floorbit. Cables typed in Floorbit are kept, and one on the same switch port wins over
NetBox's, which is then skipped and counted in the import's message. If NetBox doesn't answer, the
last import stays.

On a hosted Floorbit, the [local agent](agent.md#cables-through-the-agent) reads NetBox on the event
network and sends the cables.

Other inventory plugins can offer cables too, with a `cables()` method (see
[plugins.md](plugins.md)). The demo plugin has a cable for every demo seat.

## Cables drawn on the floor plan

The editor draws the cables on the plan, each on its layer: network cables (to seats, and uplinks
between switches) on **Network**, power cables on **Electrical**. Turn a layer off under Layers to
hide its cables. The colour says the medium (cyan copper, green fiber, light DAC, amber dashed power,
grey when the type is not known) and a thicker line a faster cable.

- **Automatic cabling** (on by default) draws a cable from the switch to every seat whose port is
  known: from the cables here, from NetBox, and from the port descriptions on the switches. The cables
  of one seat block run together down the end of the block nearer the switch, then along each
  straight row in a lane and into its seats from that side (see **Where seat cables plug in** below).
  A bent row, a U or an L with chairs has a lane that bends with it. Rows without a lane (paths, a
  row on its own without chairs, seats placed freely) are reached along the side of the block that faces the switch; coming from above or below,
  the far half is reached round the end of the block, so no cable crosses the near row. A dot on the
  seat's edge shows where each cable plugs in. Cables that share a run are drawn side by side like a
  ribbon, each its own thin line, with the number of cables on each run; the cables that turn off
  first run on the side they turn to, so they peel off without crossing. Moving a switch or a
  seat block takes its cables along at once. Venues that patch seats through panels can turn it off under Settings > Cabling
  (`CABLE_AUTO=false`) and draw the cables they want with the Cable tool. A cable that names a patch
  panel runs through it once the panel is on the plan: right-click the floor and pick **Put patch panel
  … here**; drag it to move it.
- **The Cable tool** (`C` in the tool rail): **Network cable** starts at a switch; click a seat, a
  seat block (one cable per seat, the ports counting up, as above) or another switch (an uplink), then
  give the port, the type (copper, fiber or DAC) and the speed. **Power cable** starts at a
  distribution board (the power layer comes on); click a seat block or a switch and pick the circuit,
  or make a new one ([power.md](power.md)).
- **Routing by hand**: click a cable to select it, then click it again and drag to add a bend; drag a
  bend to move it (it snaps to the grid, unless snapping is off); double-click a bend to remove it.
  A cable with bends of its own keeps them when the seat behind its port changes. The side panel of a
  selected cable changes its **ends** (switch and port, seat) and how it is **drawn**: straight (end to
  end; its bends are kept for later), angled or rounded. Right-click a cable for round or square corners, **Back to the automatic route**, or to delete it (an imported cable is
  changed in NetBox; one from a port description goes away with the description). Everything can be
  undone with Ctrl+Z.

### Where seat cables plug in

Each seat shows its chair as a small grey square on the side people sit (a row's **Chairs**, see
[halls.md](halls.md)). A straight row's cables run in a lane along the row and plug into the seats from
that side. Pick it per row under **Cables connect**, or for every row of a block on the Block tab:

- **Auto**: away from the chairs. A row without chairs takes the side with a gap to the next row (the
  smaller gap when both sides have one, so a cable gap before the aisle), or the seam when the next row
  touches. A row on its own without chairs keeps the route along the block.
- **Behind**: away from the chairs, behind the table. A row without chairs goes by Auto.
- **Chair side**: where the player sits.

The lane runs in the middle of the gap to the next row, on the seam when the rows touch, and half a seat
out at the block's edge.

A bent row (an arc, a U, an L) with chairs has a lane that follows it, half a seat out from its seats
on the side **Cables connect** picks, square round a U's or an L's corners. Its cables come in at the
end of the row that makes them shorter and run along it to their seat. A path row has no chairs of its
own, so it keeps the route along the block until it gets some.

**Set chairs automatically** on the Block tab sets the chairs of all straight
rows: rows that share a table (touching, or with a gap of a seat or less) sit on its outer sides; a row on
its own faces its bigger gap. A row in the middle of three or more keeps its side. Undo puts them back.

The drawing is kept apart from the cables (data.json `cable_routes` and `patch_panels`), so importing
from NetBox again keeps the bends.

## Who can do what

Everyone who can see the floor plan can see the cables and print labels. Adding, changing,
removing, importing and routing them on the plan need `floorplan.edit` (leads and admins). Each change is in the audit log
under **cables**, with the cable's label and route.

## API

- `GET /api/cables?q=&seat=&ids=`: the cables, and `sources`, the plugins that can import them.
- `POST /api/cables`, `PATCH /api/cables/<id>`, `DELETE /api/cables/<id>`.
- `POST /api/cables/import`: answers `{"imported", "errors"}`.
- `GET /api/cables/check`: the plan against the last port read: `{"last_poll", "blocks", "missing", "down",
  "unplanned", "conflicts", "unread"}`; each list is `{"count", "rows"}` (at most 200 rows).
- `GET /api/cables/clients?read=1`: the last MAC table read, `{"as_of", "reading", "started", "error",
  "switches", "clients", "failed", "unplanned", "moved", "shared", "no_port", "empty", "ignored"}`; a
  `shared` row is `{"switch", "port", "seat", "cable", "macs", "desk_switch"}`; `read=1` starts a new
  read when the last is two minutes old. Needs `seats.view`.
- `GET /api/cables/clients/ignored`, `POST /api/cables/clients/ignored` `{mac, note}`,
  `DELETE /api/cables/clients/ignored/<mac>`: the machines left off the lists (`floorplan.edit` to change).
- `GET /api/cables/walk?switch=&since=`: the ports of a switch that came up since `since`
  (`{"ups": [{"port", "at", "how"}], "syslog", "since"}`); without `since` the walk begins now.
- `POST /api/cables/assign`: `{"seat", "switch", "port", "swap"}`: the seat is on that port. 409 with
  `other_seat` when it is another seat's, unless `swap`.
- `POST /api/cables/block`: `{"block", "switch", "first_port", "order": "rows" | "snake", "reverse", "rows",
  "dry_run", "replace"}`. Answers `{"block", "cables": [{"seat", "switch", "port"}], "clashes", "created", "removed"}`;
  409 when cables are in the way and `replace` isn't set.
- `GET /api/cables/labels.pdf?q=&ids=`, `GET /api/cables.csv?q=`.
- `GET /api/cable-plan?hall=`: the cables to draw in a hall: `{"cables": [{"key", "kind": "lan" | "uplink" | "power",
  "layer", "points": [[x, y], ...], "manual", "drawn", "corners", "media", "speed", "via", "label", "ref"}],
  "panels", "panel_names", "auto"}`, positions in % of the plan.
- `PUT /api/cable-plan/routes`: `{"routes": {"<key>": {"points": [[x, y], ...] | null, "corners": "square" | "round" | "straight"} | null}}`:
  the bends between the ends; `points: null` draws the cable on the automatic route (shown with automatic cabling
  off too), `null` forgets the drawing.
- `PUT /api/cable-plan/panels/<name>` `{"x", "y", "hall_id"}`, `DELETE /api/cable-plan/panels/<name>`.

The feature can be turned off under Settings > Features (`cables`).
