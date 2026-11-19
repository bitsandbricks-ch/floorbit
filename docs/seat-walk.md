# Seat walk-through

Before doors open, the crew walk the rows with a laptop on a cable and plug it into each seat's
socket in turn. The **Seat walk-through** page (`/seat-walk`, also linked from the Check-in page and
from Walk the row) finds the switch port for each seat from the laptop's address and keeps it. The
local agent in the hall tells Floorbit that address, whether Floorbit runs in the hall or is hosted.

## How a seat is found

1. Pick the seat block and the walking order. Seats that already have a port can be skipped.
2. Plug the laptop into the seat, wait for the link light and press **Locate** (or Enter).
3. The page sends the browser to the local agent once with a one-time code. The agent sees the
   laptop's own IP, reports it with the code and sends the browser straight back. This takes well
   under a second on the hall network.
4. Floorbit finds the laptop's MAC (the core's ARP table) and then the access port that MAC is on
   (the access switches' MAC tables). The page shows a loader while it looks, then either **the seat
   and its switch port**, or **why it failed**.
5. **Next seat**, and so on. **Undo** forgets a seat's port again.

Where the answer comes from, freshest first:

| Way | When it is used | How long |
| --- | --- | --- |
| **The switch itself** | SSH port actions are on and a switch login is stored ([credentials](credentials.md)) | 1 to 3 seconds |
| **The monitoring source** | Telemetry or LibreNMS, through the local agent when one is enrolled | as fresh as its last poll of the MAC tables: seconds to a few minutes |

The switch read asks the switch of the last seat first (a row is mostly on one switch), then the
seat's switch in the patch plan, then the other switches. Ports that lead to another switch (LLDP or
CDP neighbours, port channels) are skipped.

The laptop is identified again at every seat, as some seats may give it another address. While
the address stays the same, the MAC found at the last seat is used again and only the MAC tables are
asked. An answer that still
names the last seat's port comes from a MAC table nobody read again yet: Floorbit doesn't take it and
keeps asking for up to 90 seconds.

## Why always through the agent

Floorbit itself often doesn't see the laptop's own address: behind NAT or on a hosted Floorbit it
sees the hall's public address, behind a reverse proxy the proxy's. The agent is on the event
network and sees the laptop as it is. Going through it every time, self-hosted or not, keeps the walk
the same everywhere. Floorbit never takes the request's own address for the laptop's.

Nothing has to be set up for it. Floorbit works out how the laptop reaches an agent:

- **The walk page itself came through an agent** (the laptop opened the check-in name or an agent's
  address): the agent's front door already told Floorbit the laptop's address. Done, no trip.
- **Otherwise** the laptop opens `http://<check-in name>/floorbit/hello/<code>` once and comes
  straight back. The check-in name (`CHECKIN_ADDRESS`) is the one on the seat cards; every agent's
  front door answers it.
- **No check-in name set:** the address browsers in the hall last reached an agent at. Each agent's
  front door learns it from the requests it answers and reports it.

A code is good for ten minutes, is used once, and only a signed-in page with `seats.edit` makes one.
The agent sends the browser back only to the Floorbit it is enrolled with.

### Or type the laptop's MAC

Without an agent, or when it is down, type the laptop's MAC on the setup page. Floorbit then skips
the address and looks for that MAC in the switches' MAC tables (or the monitoring source's) directly.

## Before you start

- **Portfast.** The seat ports need `spanning-tree portfast` (or edge port). Without it a port stays
  blocked for about 30 seconds after the cable goes in.
- **Wi-Fi off.** The laptop's address must be the one on the cable. With `CHECKIN_ALLOWED_NETWORKS`
  set, the page refuses addresses outside the seat networks.
- **A local agent** with its captive port on and its address in the hall set, or the laptop's MAC
  typed in.

## Per event, cleared a day after

A seat's port is kept for the event that was open when it was found (see [tenants and
events](tenancy.md)), in the same place attendee check-ins keep theirs. A new event starts empty.

One day after the event ends, Floorbit clears the seat ports of that event, the ones from the walk
and from check-ins alike. The end is the event's end in its [schedule](schedule.md); without one,
the time the event was closed. Each clearing is in the audit log.

The patch plan ([cables](cables.md)) is not cleared: it is what the crew planned, not what was found.
Where the patch plan names another seat for a port, the plan wins on the floor plan, so the page
offers to correct the plan.

Who may: reading needs `seats.view`, locating and saving needs `seats.edit`.
