# IP and MAC history

**Network > IP and MAC history** (`/endpoints`) says where each machine was seen: its MAC, the IPs
it had, the switch port it was plugged into, the seat on that port, and when. Search by an IP (or
its start: `10.4.12` finds the range) or a MAC in any notation (`aa:bb:cc`, `aabb.cc`, `AA-BB-CC`,
or a part of one). **Go to** (Ctrl K) finds IPs and MACs too.

A port's history (`/endpoints?device=sw-a-01&port=Gi1/0/1`) and a seat's
(`/endpoints?seat=A-1`) show who was plugged in there over the event.

Only roles with *See who sits where* (`seats.view`) see it.

## Where it comes from

Every minute, from the [Telemetry](telemetry.md) plugin's picture: each MAC on the access port that
learned it (not an uplink or an LLDP/CDP neighbour, the port with the fewest MACs when several are
left), with the IPs the core's ARP gives it. With a local agent, the agent sends it to the hosted
Floorbit. A MAC that is only in ARP (a firewall, a server behind a router) is kept with the device
that has the ARP entry and no port. ARP and the MAC tables are read in separate rounds, so a
machine can be in ARP a round before its port is known, or stay in ARP a little after the access
switch forgot it: those port-less sightings belong to the port's row and don't get one of their own.

A row stays open while the machine keeps being seen there, and a new one starts when it moves to
another port, gets another IP, or was gone for 15 minutes. The seat is the one on that port when
it was seen (the patch plan, or the port a check-in learned); a seat's history also shows what was
on its port before the seat was known.

## Storage

In Floorbit's database (SQLite or Postgres, table `floorbit_endpoints`), kept for 7 days
(`FLOORBIT_ENDPOINT_DAYS`, 1 to 365).
