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

The firewalls are the inventory's devices with the role **Firewall** (from NetBox, or added by
hand). A seat's range is the most specific one its IP is in, the way the core's routing table picks
it. Changing ranges needs `floorplan.edit`; every change is in the audit log.

## Health

Each firewall's state comes from the monitoring source's device list (LibreNMS, or the local
agent on a hosted Floorbit), read at most every 15 seconds, matched by name like the status
monitor does. A range takes the first firewall in its line that isn't reported down. A firewall
the source knows nothing about counts as up, since the core would still route to it, and the range
says **Not read** instead of **As planned**. When the source can't be read at all, the page says
so and every range shows its planned firewall.

Firewalls don't need to be on the floor plan: most stand in the rack behind the core.

## Not yet

- Importing the ranges from NetBox (prefixes with a firewall field) is not built yet.
- Floorbit doesn't read the core's routing itself: "now" is what the plan and the health say the
  core should do.
