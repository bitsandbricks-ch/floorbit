# Network segments

A segment is a VLAN and its IP range, for example VLAN 110 with 10.10.0.0/22. Segments tell
Floorbit which VLAN a PC's IP is on, so a check-in can ask the switches for that one PC in that one
VLAN instead of walking every ARP and MAC table (issue #946, used by the check-in lookup in #947).

Find them under **Telemetry > Lookup segments** (admins only).

## Lookups are off until you turn them on

Every segment starts with lookups **off**, whether discovery found it or someone added it. Nothing
is asked of the switches by surprise: turn lookups on for the segments where attendees' PCs sit
(the seat VLANs), and leave them off for management, servers and Wi-Fi. While no segment has
lookups on, the page says so.

## Where segments come from

- **Discovery.** A switch or router's VLAN interface with an address (Vlan110, Vl110, vlanif110,
  irb.110, BVI110) becomes a proposal: its VLAN, its IP range, the VLAN's name and the device.
  Discovery adds new ones by itself; **Take from discovery** does the same on demand. When two
  devices carry the same range (a core pair), the first one names it.
- **By hand.** Give the VLAN (1 to 4094), the IP range (IPv4, /8 to /30; host bits are dropped, so
  10.10.1.7/22 becomes 10.10.0.0/22) and a name.

Discovery corrects its own segments when the facts change (a renamed VLAN, a new interface index).
A segment someone changed by hand (VLAN, range or name) is never overwritten. Turning lookups on or
off doesn't count as a change of the facts.

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
