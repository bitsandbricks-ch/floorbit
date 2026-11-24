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

Where the answer comes from, in the order Floorbit asks:

| Way | When it is used | How long |
| --- | --- | --- |
| **The monitoring source** | Telemetry or LibreNMS, through the local agent when one is enrolled | as fresh as its last poll of the MAC tables: seconds to a few minutes |
| **A few SNMP requests** | the laptop's IP is in a [network segment](segments.md) with lookups on | under a second per switch |
| **The switch itself, over SSH** | SSH port actions are on and a switch login is stored ([credentials](credentials.md)); the last resort, for switches that don't answer SNMP | 1 to 3 seconds |

The SNMP requests go out at any time during a walk: the check-in window only holds back the
attendees' own check-ins. They ask the switches of the seat's row first, then the rest of its
block, then every other switch with the VLAN.

The SSH read asks the switch of the last seat first (a row is mostly on one switch), then the
seat's switch in the patch plan, then the other switches. Ports that lead to another switch (LLDP or
CDP neighbours, port channels) are skipped.

The laptop is identified again at every seat, as some seats may give it another address. While
the address stays the same, the MAC found at the last seat is used again and only the MAC tables are
asked. An answer that still
names the last seat's port comes from a MAC table nobody read again yet: Floorbit doesn't take it and
keeps asking for up to 90 seconds.

## Watching what it does

While the walk runs, the page shows:

- **At the top:** the agent address to open on the laptop (with a copy button), the laptop's IP and
  MAC that Floorbit is looking for, and which agent saw it.
- **A flow strip:** laptop, MAC, the monitoring tables, then the switches of the row, the block and
  the rest of the VLAN (and SSH when it comes to that), up to the seat. The step being asked right
  now is marked.
- **What Floorbit is doing:** every step with its time and how long it took: which agent saw the
  laptop, whether the monitoring tables had it, which switch was asked in which group and what it
  said (not there, only on an uplink, no answer, found), an answer that still names the last seat's
  port, and the next try. **Everything** shows each try; **Steps** folds the waits. **Copy** puts the
  whole trace on the clipboard, for a bug report.

The steps reach the page live while the lookup runs. Only signed-in pages that may read seats see the
laptop's IP and MAC in them; on other pages they are left out.

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
- **A local agent** in the hall, or the laptop's MAC typed in.

## Walking with several people

Pick your rows and press **Start**. The page then watches for the cable: plug it into the seat's
socket and the page finds the port on its own and moves on to the next seat. There is no Locate
button to press while it watches (it stays for a manual retry after five minutes without a port).

Several people can walk at once, each with their own rows. The page lists every row in the hall with
how many of its seats have a port, who walks it and at which seat they are now. A row someone else
walks can't be started twice; **Take them over** moves those rows to you, for when the other walker
left without stopping. A walk that has not said where it is for ten minutes counts as ended.

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
