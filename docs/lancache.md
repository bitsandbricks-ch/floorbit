# LAN cache

The **LAN cache** plugin watches a [lancache.net](https://lancache.net) cache from the local agent
(docs/agent.md), in the hall, and sends Floorbit hall-wide numbers only. It feeds:

- four dashboard widgets: this hour's hit ratio, what the cache served per hour, the cache
  machine (cache, lancache-dns, disk) and popular downloads;
- the **LAN cache** view, for a dashboard pane or a widget opened up: the same numbers over a
  chosen range, files the cache isn't keeping, lancache-dns lookups, and clearing the cache;
- the cache numbers on **Games**, the stats wall and the health wall (docs/games.md);
- **DNS analytics** (docs/dns.md), from lancache-dns's query log;

It is a plugin like any other: turn it on under **Settings > Plugins > LAN cache** and fill in the
paths as the agent sees them. The agent picks the settings up on its own (docs/agent-plugins.md).
Floorbit reading `LANCACHE_LOG` itself (docs/games.md) still works for a Floorbit that runs in the
hall; with a hosted Floorbit, use the plugin.

## On the agent

Mount the cache's folders into the agent's container. Read-only is enough unless you want to
clear the cache from Floorbit:

```yaml
services:
  agent:
    volumes:
      - /srv/lancache/logs:/lancache/logs:ro
      - /srv/lancache-dns/logs:/lancache/dns:ro
      - /srv/lancache/cache:/lancache/cache/cache:ro      # :rw to allow clearing
    environment:
      # Only if the cache may be cleared from Floorbit:
      FLOORBIT_AGENT_ALLOW_ACTIONS: lancache.clear_cache
```

| Setting | What it is for |
| --- | --- |
| Access log | The cache's `access.log`: bytes from the cache and from the internet per service and hour, popular downloads, files it isn't keeping. |
| DNS query log | lancache-dns's bind query log (`querylog` on): lookups of the cached services, and the sites for DNS analytics. Empty: no DNS numbers. |
| Cache folder | nginx's cache folder (with the hash folders `00` to `ff`): disk use, and clearing. |
| Cache address | The cache's name or address on the event network. The agent asks `/lancache-heartbeat` there every round: it should answer `204` with an `X-LanCache-Processed-By` header. |
| lancache-dns address | The agent asks it for `lancache.steamcontent.com` and checks the answer is the cache. Needs the cache address. |
| Players before a download or site is named | 5 by default. |
| Seconds between reads | 30 by default. |

The agent remembers where it stopped reading each log (in its state folder), so a restart carries
on there; a rotated log is read from the top.

<!-- TODO: check both log formats against a running lancache monolithic and lancache-dns before an event. -->

## Privacy

Client addresses never leave the hall. The agent counts players per hour as keyed hashes it keeps
in memory, and sends only:

- bytes and requests per service and hour, and how many players there were;
- a download (a Steam depot, or the first part of a path) only once **5 or more players** fetched
  it in the window; everything else is one "other downloads" line;
- files fetched from the internet 3 times or more in one hour (by service and path, no player);
- DNS lookups per site and hour once 5 or more players looked the site up, in the format DNS
  analytics already uses.

Floorbit refuses a `stats` payload that holds an IP or MAC address (docs/agent-plugins.md). The
`status` payload (disk, heartbeat, DNS check) is about the cache machine, not about players.

## Clearing the cache

**Clear the cache** on the page (admins) empties the cache folder: only nginx's two-letter hash
folders, nothing else in it. It needs two yeses: the admin role in Floorbit, and the hall allowing
it on the agent with `FLOORBIT_AGENT_ALLOW_ACTIONS=lancache.clear_cache` and a writable mount. The
agent clears in the background; the page shows how far it got. Players then download everything
from the internet again until the cache has filled up. Each request is in the audit log.

## Files the cache isn't keeping

The page lists files that came from the internet three times or more within an hour. That usually
means the disk is full, the slice size is wrong, or the service changes its files (some launchers
do on every update). A few during a big release are normal.
