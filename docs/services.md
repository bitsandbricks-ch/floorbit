# Services

Monitoring › Services (`/services`, issues #471, #889, #1337): every service the event depends on,
in one list. The internet lines, the DNS resolvers, the internet sites players need, the LAN cache,
the [game servers](game-servers.md) and the crew's [own checks](#own-checks) are set up here; DHCP,
the [firewalls](firewalls.md) and what health plugins watch are listed too, set up where they come
from: a group whose services all come from one place (the firewalls, DHCP) says where once, by its
title. A plugin's LAN cache is not listed a second time next to the page's own LAN cache row. Each also shows on the [service health](health.md) widget and so in its alerts (the sites as one tile).

The page is one list, one row per service: its state, name and address, its tags, the number that
matters (how full, how fast, how many players), the last half hour as a line, and what can be done
with it. Four tiles on top count down, look, up and all. Rows are grouped by **type**, **tag** or
**state** (down first). A search box (names, addresses and tags) and **All / Not up / Up** narrow
the list. **Add service** asks which kind first: an internet line, a DNS resolver, an internet site
or an own check (`floorplan.edit`), or a game server (`settings.manage`). **Check now** checks
everything at once, the health plugins' services too (`floorplan.edit`).

Clicking a row opens its **panel** (beside the list on a wide screen, from the side on a phone):
what the old Service health page showed (the numbers, "full in about 40 minutes" for a pool that
fills, since when it is like this, until when its alerts are muted), its tags, and **Change**,
**RCON console**, **Mute alerts 1 h** (`incidents.work`) and a link to Problems.

## Tags

Any service can have up to 8 tags of up to 24 characters, also one a plugin watches: a stage, a hall,
"Sponsor". Type them in the panel (`floorplan.edit`); **Group by: Tag** then lists each tag's
services, a service with two tags under both and one without under **No tag**. Tags are kept in
data.json under `service_tags`, by the service's id (`uplink:<id>`, `check:<id>`, `dhcp-players`,
...); removing a service set up here removes its tags.

## Own checks

For anything else the event needs: a stream encoder, a tournament site, a voice server. Each is
run by the [local agent](agent.md) from the event network, every check:

| Check | What the agent does | Down when |
| --- | --- | --- |
| **Ping** | Three ICMP echoes, with the unprivileged ping socket Linux and Docker allow (`net.ipv4.ping_group_range`), no root | none comes back |
| **TCP port** | Three connects to any port; nothing is sent | none gets through |
| **UDP port** | One question: a DNS query, an NTP time request, a Steam/Source server query, or an empty datagram | the port is closed (ICMP unreachable), or a question gets no answer. With an empty datagram silence counts as up: UDP gives nothing more |
| **HTTP(S)** | One plain `GET`, no headers or body of yours; reads up to 64 kB only to look for **Page contains** | the status is outside **Expected status** (default 200-399), the text is missing, the certificate is not valid, or no answer |

Each turns amber (look) when slower than **Look when slower than** (100 ms for ping, 200 ms for
TCP and UDP, 1 s for HTTP), at 20 % loss, or for HTTPS when the certificate ends within **Look when
the certificate ends in** days (14). Only the status, the time and the certificate's end come back
from the agent, never a page. **Test** in the form runs it once before it is saved. The addresses
the agent may reach follow its own `FLOORBIT_AGENT_PROBE_NETS`, never this machine or link-local.

## Internet lines

| Field | Meaning |
| --- | --- |
| Name | Like the provider: `Provider A`. |
| Device, port | Where the line comes in, from the inventory: the core switch, a router or a firewall (`core-01`, `Te1/0/48`). A device can have several lines, so each firewall can have its own. |
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
just added is checked when the page next loads. The local agent sends every probe from the event
network, so a hosted Floorbit measures the event's lines, not its own. **Check now** on the page
checks everything at once, the plugins' services too (`floorplan.edit`).

### Which agent checks

With several agents (a site each, or two in one group), every check runs from one place, so its
numbers don't jump from agent to agent (issue #1444):

- An own check's **Checked from** picks it, like telemetry's **Collected by**: the agents with a tag
  (the first one connected, by id), or one agent. While nobody it names is connected, the default
  below takes over.
- By default, a check of an inventory device (its name or management address) runs on the agent
  that collects that device; anything else, and every line, resolver and site, on the group's
  primary agent. It moves only on failover.

### Without an agent

The Floorbit server never sends a probe, game server query or RCON command itself: the agent is the
only way it reaches the event network. Without a connected agent, lines, resolvers, sites, own checks
and game servers show grey, "not checked", not red. Only demo mode answers with made-up values.

### What the agent may reach

The agent never sends a probe to link-local addresses (`169.254.0.0/16`, `fe80::/10`), to `0.0.0.0`
or to multicast, also not through IPv6 that carries one of those inside (`::ffff:`, NAT64
`64:ff9b::`, 6to4 `2002::`). Set `FLOORBIT_AGENT_PROBE_NETS` on the agent to a comma-separated list of networks (for
example `192.0.2.0/24,198.51.100.0/24`) and it reaches only those. Host names are resolved first and
the address is checked, so a name can't get around the list.

Adding and changing lines, resolvers and sites needs `floorplan.edit`; each change is in the audit log.
