# Services

Network › Services (`/services`, issue #471): the internet lines, the DNS resolvers, the internet sites
players need and the LAN cache, with whether they answer, how full the lines are and how fast. Lines
and resolvers also show on the service health wall (`/health`) and so in its alerts; the sites show
there as one tile.

## Internet lines

| Field | Meaning |
| --- | --- |
| Name | Like the provider: `Provider A`. |
| Router or firewall, port | Where the line comes in, from the inventory (`core-01`, `Te1/0/48`). |
| Capacity | What the line is booked for, in Mbit/s (not the port speed). |
| Probe host, port | Optional: a server always reachable over the line. Port 53, 80, 443 or 853. |

Floorbit reads the port from the monitoring source (the same reads as the topology): up or down,
traffic in (from the internet) and out, and the busier direction against the capacity. With a
probe host it connects to it five times per check for the average time and how many got no
answer. ICMP ping would need root, a TCP connect to a port the host always answers measures the
same path without it. Floorbit never sends data on those connects.

A line is **down** when its port is down or every probe got lost, **look** (amber) at 80 % used,
20 % loss, 100 ms or port errors.

## DNS resolvers

An address and a name that must always resolve (like `example.com`). Floorbit sends one A query per
check and keeps the time and the answer code. A resolver is **down** when it doesn't answer, or
answers anything but addresses; **look** from 200 ms.

## Internet sites

Sites the players need, like search, game stores and voice chat: a name, a host and a port (53, 80,
443 or 853). Floorbit connects to each three times per check and keeps the average time and how
many got no answer. When players say "the internet is down", this shows whether it is the lines or
one site. A site is **down** when no connect gets through; **look** from 150 ms or 20 % lost.

**Add the usual sites** (shown while the list is empty) adds Google, Cloudflare, YouTube, Twitch,
Discord, Steam, Epic Games, Riot Games and Battle.net; change or remove any of them like your own.
On the health wall they are one tile: how many answer, which ones don't, and the median time.

## LAN cache

What Floorbit read from the cache's access log this hour (see [games.md](games.md),
`LANCACHE_LOG`): the share served from disk and how much it served. With `LANCACHE_CACHE_DIR`
pointing at the cache's disk (mounted read-only), also how full it is; amber from 90 %. The cache is
also a tile on the [service health wall](health.md), so a disk filling up during the event pages the
crew before downloads start to miss.

## Checks

Every `SERVICES_INTERVAL` seconds (default 30, at least 10), in the background. A line or resolver
just added is checked when the page next loads. With a local agent enrolled the agent sends the
probes from the event network, so a hosted Floorbit measures the event's lines, not its own.
**Check now** on the page checks everything at once (`floorplan.edit`).

### What the server itself may reach

Without an agent, the Floorbit server sends the probes, game server queries and RCON commands
itself. It never sends them to link-local addresses (`169.254.0.0/16`, `fe80::/10`, where clouds keep
their metadata service), to `0.0.0.0` or to multicast, also not through IPv6 that carries one of
those inside (`::ffff:`, NAT64 `64:ff9b::`, 6to4 `2002::`). Set `PROBE_NETS` to a comma-separated list of
networks (for example `192.0.2.0/24,198.51.100.0/24`) and it reaches only those: set it on a hosted
Floorbit so that nobody can point a probe at the hosting network. Host names are resolved first and
the address is checked, so a name can't get around the list.

Adding and changing lines, resolvers and sites needs `floorplan.edit`; each change is in the audit log.
