# Network segments

A segment is a VLAN and its IP range, for example VLAN 110 with 10.10.0.0/22. Segments tell
Floorbit which VLAN a PC's IP is on, so a check-in can ask the switches for that one PC in that one
VLAN instead of walking every ARP and MAC table (issue #946, used by the check-in lookup in #947).

Segments are the inventory's **Prefix or range** entries that have both a network and a VLAN ID
(**Inventory**, type *Prefix or range*). There is no separate list: a prefix is a segment as soon as
it knows its VLAN.

## Lookups are off until you turn them on

Every range starts with **Check-in lookups** off, whether discovery found it or someone added it.
Nothing is asked of the switches by surprise: turn lookups on for the ranges where attendees' PCs
sit (the seat VLANs), and leave them off for management, servers and Wi-Fi. The switch is right in
the inventory's list of prefixes, and on each range's own page. While no range has
lookups on, the crew's **Check-in** page says so and links to that list.

## Where segments come from

- **Discovery.** A switch or router's VLAN interface with an address (Vlan110, Vl110, vlanif110,
  irb.110, BVI110) gives its network's range the VLAN. Discovery adds that range to the inventory
  by itself, with lookups off. When two devices carry the same range (a core pair), the first one
  names it.
- **By hand.** Add a *Prefix or range* in the inventory with a VLAN ID (1 to 4094) and a prefix
  (IPv4, /8 to /30; host bits are dropped, so 10.10.1.7/22 counts as 10.10.0.0/22).

Discovery corrects its own ranges when the facts change. A field someone changed by hand is never
overwritten, the same as for everything discovery and plugins feed into the inventory. Turning
lookups on or off is up to you; discovery never touches it.

An IP in more than one range belongs to the narrowest one.

## When a check-in asks the switches

A check-in (the PIN on the seat card, the captive portal, the crew's [seat walk](seat-walk.md))
gives the PC's IP. When the tables (LibreNMS first, then Telemetry) don't know that PC yet, Floorbit
asks the local agent to find it:

1. The segment of the IP, the narrowest that holds it. No segment, or lookups off there: no
   lookup. The crew's **Check-in** page shows the check-in with a to-do: type the MAC or pick the
   port.
2. The MAC, from the core's ARP entry on the segment's VLAN interface (from discovery). Skipped when
   the MAC is known already.
3. The switches, one at a time, until one learned the MAC on a port that isn't an uplink:
   - the switches serving the seat's row (its learned ports, the patch plan's cables and the
     [switch areas](switch-areas.md));
   - then the rest of its block;
   - then every other switch that carries the VLAN.

   Uplinks are skipped: trunk ports, LLDP or CDP neighbours, and ports with more than 4 MACs in the
   telemetry picture.

The port found goes to the check-in, to the IP and MAC history ([endpoints.md](endpoints.md)) and,
with a PIN, to the seat. The same IP or MAC asked again within a minute shares one lookup.

### The check-in window

Attendees' check-ins ask the switches only while the window is open:

- from doors open (the event's start in the [schedule](schedule.md)) for 6 hours;
- kept open for 30 minutes after any check-in while it is open;
- or opened by hand on the **Check-in** page (**Open for 6 h**), for example for a late arrival
  wave. Closing it there ends what was opened by hand.

The crew's seat walk asks at any time.

While a segment has lookups on, Telemetry walks the full ARP and MAC tables only every 15 minutes
when it polls them ([telemetry.md](telemetry.md#who-polls-the-switches)): the check-ins don't wait for them any more.

## How the agent asks the switches

The agent asks with single SNMP GETs, never table walks (`floorbit/telemetry/snmpget.py`):

1. **IP to MAC** on the core: the ARP entry `ipNetToMediaPhysAddress.<VLAN ifIndex>.<IP>`.
2. **MAC to bridge port** on an access switch: `dot1dTpFdbPort.<MAC>` (Cisco: in the VLAN's own
   bridge, `community@110` for SNMPv2c or the `vlan-110` context for SNMPv3), or
   `dot1qTpFdbPort.<VLAN>.<MAC>` on Q-BRIDGE switches.
3. **Bridge port to interface**: `dot1dBasePortIfIndex.<port>`.

One request at a time per switch, a 2 second timeout and no retries, so a lookup never loads a
switch. Logins come from the device's telemetry settings and are never logged.
