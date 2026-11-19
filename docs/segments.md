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

## How the agent asks the switches

The agent asks with single SNMP GETs, never table walks (`floorbit/telemetry/snmpget.py`):

1. **IP to MAC** on the core: the ARP entry `ipNetToMediaPhysAddress.<VLAN ifIndex>.<IP>`.
2. **MAC to bridge port** on an access switch: `dot1dTpFdbPort.<MAC>` (Cisco: in the VLAN's own
   bridge, `community@110` for SNMPv2c or the `vlan-110` context for SNMPv3), or
   `dot1qTpFdbPort.<VLAN>.<MAC>` on Q-BRIDGE switches.
3. **Bridge port to interface**: `dot1dBasePortIfIndex.<port>`.

One request at a time per switch, a 2 second timeout and no retries, so a lookup never loads a
switch. Logins come from the device's telemetry settings and are never logged.
