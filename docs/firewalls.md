# Firewalls

Network › Firewalls (`/firewalls`, issue #470). For events where the core spreads the seats over
several firewalls: the core policy-routes each seat range to its firewalls (issue #866). A range is
any span of addresses, not only a CIDR block. A range over several firewalls is cut into equal
**parts**, one per firewall in their order: a /24 over four firewalls sends each quarter to its own.
Where the core also moves a part while its firewall is down, the range names that fallback. Floorbit
keeps the plan and holds it against the firewalls' health, so the crew sees at a glance which parts
are off their firewall and which firewall a seat's traffic takes.

## What you see

- **A card per firewall**: up or down, the parts it serves now and how many seats that is, the
  parts it is planned for (stand out while it is down) and the parts it took over from a firewall
  that is down.
- **The ranges**: each range with its parts, the firewall each takes now and whether that is as
  planned, on its fallback, or no firewall up at all, and the fallback if any. Parts not on their
  planned firewall are listed at the top.
- **Which firewall?**: once a range is planned, type an IP address or a seat at the top of the
  page. It answers with the range and the part the address is in, the firewall it goes through
  now, whether that is as planned, and the fallback (`GET /api/firewalls/lookup?q=`). A seat is
  looked up through its IP, which the answer never shows; without **See seats** (`seats.view`) a
  seat's answer leaves out the range and part too, since a small part narrows the IP down.
- **On the floor plan**: the seat panel says which firewall the seat takes, and when it failed over,
  which one it should take, for everyone who sees the plan, whenever a range covers the seat. It
  links to **Which firewall?** for that seat. The seat's IP is never shown there for this.

## The plan

A firewall range is an inventory **prefix** with firewalls set (Mike, 2026-11-24): a network is
written down once, under **Inventory › IPAM › Prefixes**, with its VLAN, gateway, group, tags and
notes, and the firewall plan on top. Planning a range here for a network the inventory has already puts
the plan on that prefix; otherwise a prefix is made for it, and it goes again when its plan is removed.
A prefix NetBox or discovery keeps stays when its plan goes.

| Field | Meaning |
| --- | --- |
| Range | A network, like `192.0.2.0/27`, or from-to, like `192.0.2.0-192.0.2.128`. A from-to that is exactly one network is written as that network. A host address is turned into its network. IPv4 and IPv6. |
| Name | Optional, like `Block A`. |
| Firewalls | The firewalls the core routes the range to, in order (at most 16). With several, the range is cut into equal parts, one per firewall: the first part to the first firewall, and so on. Addresses that don't divide evenly go one each to the first parts, so a /24 over three firewalls is `.0-.85`, `.86-.170` and `.171-.255`. |
| Fallback | Optional: where the core moves a part while its own firewall is down, in order. Left empty, the part is down with its firewall. |
| Switches and switch groups | Optional: what this range is for. See [Seats in the wrong range](#seats-in-the-wrong-range). |

The firewalls are the inventory's devices with the role **Firewall** (from NetBox, or added by
hand). A seat's range is the narrowest one its IP is in, the way the core picks it. Ranges may sit inside
each other, but two that only cross are refused: the addresses in between would be ambiguous. A range is an inventory item: **Change** (or **Switches** on an imported one) opens its page in the inventory, with its parts, where each runs now, and its plan, saved with the save bar. **Add range** stays a dialog here. Changing ranges needs `floorplan.edit`; every change is in the audit log.

### Ranges from NetBox

Where the ranges are kept in NetBox, every inventory sync (on its schedule, or **Sync now** on the
Inventory page) reads them with the prefixes; there is no separate import (issue #1347).
Give each prefix the custom field **`floorbit_firewalls`** (Customization › Custom fields, on
IPAM › Prefix):

- a **text** field with its firewalls in order, like `fw-01` or `fw-01, fw-02` (the prefix is cut
  into equal parts over them), or
- a **multiple objects** field of devices, picked in order.

Prefixes with the field empty are left out. The prefix's description becomes the range's name. The
firewalls must be devices with the role Firewall in the inventory (NetBox feeds it), and a prefix that
names one Floorbit doesn't know is skipped and counted.

Each sync replaces what the last one brought, so a prefix taken out of NetBox goes here too. When NetBox
can't be read, the last ranges stay and the sync goes on. Ranges planned in Floorbit stay as they are, and a prefix for a network
planned here already is skipped. Imported ranges say **From NetBox** and are changed there. On a hosted
Floorbit the local agent asks the event's NetBox (an agent with `firewall_feeds`). The inventory sync's report says how many ranges came
(`firewall_ranges` on the NetBox report: `added`, `errors`).

### Seats in the wrong range

Each switch stack usually has its own seat ranges, and stacks come in sets (a colour, a switch type)
that are [inventory groups](inventory.md#groups-and-tags). A seat patched to the wrong port, a port
in the wrong VLAN, or a player's own router puts a PC in another stack's range: it works, but on the
wrong firewall. Floorbit compares every seat's address with its switch's ranges, and a seat outside
them shows under **Problems › Needs attention** with the range it is in instead (or "outside every
planned range", usually a router of its own) and its switch port. Three or more such seats behind
one switch are one item for the switch: check its VLAN.

Nothing needs setting up: a switch's range is the one most of its PCs are in right now, once at
least 3 of them are and they make 60 % of its PCs in a range ("most of sw-g1 is in …"). Where DHCP
hands out addresses regardless of the switch, no range is that clear and nothing is flagged; a seat
in no range at all isn't judged on a guess.

A range can also name the **switches and switch groups** it is for; that wins over the guess. Name
the group (Green) and every switch in it, and in its subgroups, uses that range. When most seats of
a named switch are outside its ranges, the range is set for the wrong switch: that is one item
linking here. An imported range takes its switches here too (**Switches**); they are kept across
syncs. The items name ranges, never a seat's IP.

## On the floor plan

Once ranges are planned, the floor plan has a **Firewalls** switch. It rings every seat whose
traffic isn't on its planned firewall: a dashed amber ring when its part is on the fallback,
a solid red ring when neither its firewall nor a fallback is up. Seats on their planned firewall stay as they
are, so a failover shows as a patch of rings in the hall. The seat panel says which firewall the
seat takes now. The plan gets seat names and firewall names only, never the IPs.

## Health

Each firewall's state comes from the monitoring source's device list (LibreNMS, or the local
agent on a hosted Floorbit), read at most every 15 seconds, matched by name like the status
monitor does. A part takes its firewall, or the first fallback, that isn't reported down. A firewall
the source knows nothing about counts as up, since the core would still route to it, and the part
says **Not read** instead of **As planned**. When the source can't be read at all, the page says
so and every part shows its planned firewall.

Firewalls don't need to be on the floor plan: most stand in the rack behind the core.

## On the health wall

Each firewall is also a tile on the [service health](health.md) widget (under **Firewalls**): green
while it is up, red when it is down, saying which of its parts failed over or have no firewall left.
So a firewall going down pages the crew on Discord like any other service.

## Not yet

- Floorbit doesn't read the core's routing itself: "now" is what the plan and the health say the
  core should do.
