# Cables and patching

`/cables` (Settings > Cables) records which switch port goes to which patch panel port and seat,
and prints a label for both ends of each cable. Issue #97.

A cable is **switch port → patch panel port → seat**. The panel and the seat are optional: a seat
patched straight into the switch has no panel, and an uplink has no seat.

| Field | |
| --- | --- |
| Switch, switch port | Needed. One cable per switch port: a second one is almost always a typo. |
| Patch panel, panel port | Optional. A panel port needs its panel. |
| Seat | Optional, written in capitals (`A-12`). |
| Label | Printed on both ends. Left empty, Floorbit numbers the cables `C-0001`, `C-0002`, ... Labels are unique. |
| Colour, length, note | Optional. The length is 0.1 to 500 metres. |

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

Once switches are up, the Cables page checks the plan against what LibreNMS says about the ports
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
  **Patch to a seat** opens a new cable with the port and that seat filled in; **Infrastructure**
  adds a cable without a seat (a crew laptop, an access point), so the port isn't asked about again.

Ports with more than 4 MACs are uplinks or a switch under a desk, and ports cabled without a seat are
infrastructure: neither is listed. Opening the page starts a read in the background, at most every two
minutes (LibreNMS itself refreshes MAC tables only when it polls), so 4000 seats don't mean 4000 calls.
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

## Labels

**Print labels** makes an A4 PDF of 3 × 8 labels, two per cable: the switch end first, then the far
end (the seat, or the panel when there is no seat). Each label has:

- the cable's label, large;
- the end it goes on (`sw-a-01 Gi1/0/3` or `Seat A-3`), in bold;
- where the other end goes, small, and the colour and length;
- a QR code that opens the cable on this page (`/cables?cable=<id>`).

The PDF holds the cables the search shows. A cable's own window prints just its two labels. Behind a
reverse proxy, set `PUBLIC_URL` so the QR codes point at the address phones reach.

## From NetBox

When the NetBox plugin is set up, **Import from NetBox** reads `/api/dcim/cables/` and adds every
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

## Who can do what

Everyone who can see the floor plan can see the cables and print labels. Adding, changing,
removing and importing need `floorplan.edit` (leads and admins). Each change is in the audit log
under **cables**, with the cable's label and route.

## API

- `GET /api/cables?q=&seat=&ids=`: the cables, and `sources`, the plugins that can import them.
- `POST /api/cables`, `PATCH /api/cables/<id>`, `DELETE /api/cables/<id>`.
- `POST /api/cables/import`: answers `{"imported", "errors"}`.
- `GET /api/cables/check`: the plan against the last port read: `{"last_poll", "blocks", "missing", "down",
  "unplanned", "conflicts", "unread"}`; each list is `{"count", "rows"}` (at most 200 rows).
- `GET /api/cables/clients?read=1`: the last MAC table read, `{"as_of", "reading", "started", "error",
  "switches", "clients", "failed", "unplanned", "moved"}`; `read=1` starts a new read when the last is
  two minutes old. Needs `seats.view`.
- `GET /api/cables/walk?switch=&since=`: the ports of a switch that came up since `since`
  (`{"ups": [{"port", "at", "how"}], "syslog", "since"}`); without `since` the walk begins now.
- `POST /api/cables/assign`: `{"seat", "switch", "port", "swap"}`: the seat is on that port. 409 with
  `other_seat` when it is another seat's, unless `swap`.
- `POST /api/cables/block`: `{"block", "switch", "first_port", "order": "rows" | "snake", "reverse", "rows",
  "dry_run", "replace"}`. Answers `{"block", "cables": [{"seat", "switch", "port"}], "clashes", "created", "removed"}`;
  409 when cables are in the way and `replace` isn't set.
- `GET /api/cables/labels.pdf?q=&ids=`, `GET /api/cables.csv?q=`.

The feature can be turned off under Settings > Features (`cables`).
