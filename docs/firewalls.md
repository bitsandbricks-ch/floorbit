# Firewalls

Network › Firewalls (`/firewalls`, issue #470). For events where the core spreads the seats over
several firewalls: each seat range is policy-routed to its firewall while that one is up, and to the
next in line when it isn't. Floorbit keeps that plan and holds it against the firewalls' health, so
the crew sees at a glance which ranges have failed over and which firewall a seat's traffic takes.

## What you see

- **A card per firewall**: up or down, the ranges it serves now and how many seats that is, the
  ranges it is planned for (stand out while it is down) and the ones it is the backup for.
- **The ranges**: each network with its firewalls in order, the one it takes now and whether that
  is as planned, a failover, or no firewall up at all. Ranges not on their planned firewall are
  listed at the top.
- **On the floor plan**: the seat panel says which firewall the seat takes, and when it failed over,
  which one it should take (crew only, from `incidents.work`). The seat's IP is never shown there
  for this.

## The plan

| Field | Meaning |
| --- | --- |
| Range | A network, like `192.0.2.0/27`. A host address is turned into its network. IPv4 and IPv6. |
| Name | Optional, like `Block A`. |
| Firewalls in order | The first is the one the range should take, the others the failover order (at most 10). |
| Seat blocks | Optional: the blocks this range is for. See [Seats in the wrong range](#seats-in-the-wrong-range). |

The firewalls are the inventory's devices with the role **Firewall** (from NetBox, or added by
hand). A seat's range is the most specific one its IP is in, the way the core's routing table picks
it. Changing ranges needs `floorplan.edit`; every change is in the audit log.

### Splitting a network

**Split a network** plans a whole hall at once: give a network (`198.51.100.0/22`), a range size
(`/24`), optionally a name and the firewalls. Floorbit cuts the network into equal ranges and shares
them out in turn: the first range goes to the first firewall with the others as backups in order,
the second to the second firewall, and so on, the way a core usually spreads seats over a cluster.
The ranges are numbered after the name (`Seat range 1`, `Seat range 2`, ...). A range planned
already keeps its own line. One split makes at most 256 ranges.

### Importing from NetBox

Where the ranges are kept in NetBox, **Import from NetBox** reads them instead (`floorplan.edit`).
Give each prefix the custom field **`floorbit_firewalls`** (Customization › Custom fields, on
IPAM › Prefix):

- a **text** field with the firewall names in order, like `fw-01, fw-02, fw-03`, or
- a **multiple objects** field of devices, picked in order.

Prefixes with the field empty are left out. The prefix's description becomes the range's name. The
firewalls must be devices with the role Firewall in the inventory (NetBox feeds it), and a prefix that
names one Floorbit doesn't know is skipped and counted.

Each import replaces the last one, so a prefix taken out of NetBox goes here too. When NetBox can't be
read, the last import stays. Ranges planned in Floorbit stay as they are, and a prefix for a network
planned here already is skipped. Imported ranges say **From NetBox** and are changed there. On a hosted
Floorbit the local agent asks the event's NetBox (an agent with `firewall_feeds`; older agents say they can't). Every import is in the audit log.

### Seats in the wrong range

When each block has its own range, a seat patched to the wrong port, a port in the wrong VLAN, or a
player's own router puts a PC in another block's range: it works, but on the wrong firewall. Give
the ranges their **seat blocks** and Floorbit compares every seat's address with its block's ranges.
A seat outside them shows under **Problems › Needs attention**, with the range it is in instead (or
"outside every planned range", usually a router of its own) and its switch port. Three or more such
seats behind one switch are one item for the switch: check its VLAN.

A block no range names needs nothing set up: its range is the one most of its PCs are in right now,
once at least 3 of them are and they make 60 % of the block's PCs in a range. A seat of that block
in another range is flagged the same way ("most of block A is in …"). A seat in no range at all is
not judged there, since the block's range is only a guess. Where DHCP hands out addresses regardless
of the block, or a block spans several small ranges, no range is that clear and nothing is flagged.
Naming the blocks on a range always wins over the guess. An imported range takes its seat blocks here too
(**Blocks**); they are kept across imports. The items name ranges, never a seat's IP.

## On the floor plan

Once ranges are planned, the floor plan has a **Firewalls** switch. It rings every seat whose
traffic isn't on its planned firewall: a dashed amber ring when the range failed over to a backup,
a solid red ring when no firewall in its line is up. Seats on their planned firewall stay as they
are, so a failover shows as a patch of rings in the hall. The seat panel says which firewall the
seat takes now. The plan gets seat names and firewall names only, never the IPs.

## Health

Each firewall's state comes from the monitoring source's device list (LibreNMS, or the local
agent on a hosted Floorbit), read at most every 15 seconds, matched by name like the status
monitor does. A range takes the first firewall in its line that isn't reported down. A firewall
the source knows nothing about counts as up, since the core would still route to it, and the range
says **Not read** instead of **As planned**. When the source can't be read at all, the page says
so and every range shows its planned firewall.

Firewalls don't need to be on the floor plan: most stand in the rack behind the core.

## On the health wall

Each firewall is also a tile on the [service health](health.md) widget (under **Firewalls**): green
while it is up, red when it is down, saying which of its ranges failed over or have no firewall left.
So a firewall going down pages the crew on Discord like any other service.

## Not yet

- Floorbit doesn't read the core's routing itself: "now" is what the plan and the health say the
  core should do.
