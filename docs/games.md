# Game and launcher insights

What the hall plays and downloads, and how much the LAN cache saved: per launcher (Steam,
Battle.net, Riot Games, Epic Games, EA app, Ubisoft Connect, Xbox, Minecraft), the bytes the LAN
cache served for it, its traffic and its DNS lookups. It's on the **Games** page (`/games`, also
linked from Traffic) and in `GET /api/games`.

It answers questions like "is the cache pulling its weight?", "which launcher is downloading right
now?" and "how many seats play on the tournament servers?". Hall-wide only: no seat, person or
address is ever shown or kept.

## Sources

The page uses whichever of these the event has. Each one adds a column.

| Source | What it adds | Set up |
| --- | --- | --- |
| The LAN cache's access log | Bytes served from the cache's disks and from the internet, per launcher and per hour, and the hit ratio. | `LANCACHE_LOG`, below |
| [Traffic](flows.md) | Bytes and seats per launcher (by its ports), and the gaming services the event named in `FLOWS_SERVICES` (tournament servers, a game's ports). Always the last 24 hours. | The flow collector |
| [DNS analytics](dns.md) | Lookups of each launcher's sites, under the five-seat rule. | A `dns` plugin |

Launchers no source has seen are left out. A launcher can be in one column and not another: the
built-in traffic rules only know the ports Steam, Battle.net, Riot Games and Minecraft publish, and
the LAN cache only carries launchers that [cache-domains](https://github.com/uklans/cache-domains)
lists.

## The LAN cache's log

Floorbit reads the access log the [lancache.net](https://lancache.net) container writes
(`/data/logs/access.log` inside it). Mount that folder into Floorbit's container read-only and point
`LANCACHE_LOG` at the file:

```yaml
services:
  floorbit:
    volumes:
      - /srv/lancache/logs:/lancache-logs:ro
    environment:
      LANCACHE_LOG: /lancache-logs/access.log
```

Every `LANCACHE_INTERVAL` seconds (30) Floorbit reads what the log gained. It remembers where it
stopped, so a restart carries on there, and a rotated log is read from the top. A log it hasn't
seen before is read from at most 50 MB back. Each line gives the cache it belongs to (`[steam]`),
the bytes sent and whether nginx answered from disk (`HIT`, `STALE`, `UPDATING`, `REVALIDATED`) or
fetched it (`MISS`, `EXPIRED`, ...). Only answers with a 2xx status count.

Floorbit keeps per hour and per cache only those byte counts and the number of requests, in
`lancache.json` next to `data.json`, for `LANCACHE_RETENTION_HOURS` (168). The client address on
each line is never kept.

<!-- TODO: check the log format against a running lancache monolithic container before an event. -->

With the demo data on (`FLOORBIT_DEMO=1`) and no `LANCACHE_LOG`, a made-up cache serves the demo
hall, with a day of history.

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `LANCACHE_LOG` | (none) | Path of the LAN cache's access log. Empty: no cache numbers. |
| `LANCACHE_INTERVAL` | `30` | Seconds between reads (at least 5). |
| `LANCACHE_RETENTION_HOURS` | `168` | How long hourly counts are kept. |

The feature switch is **Game insights** (Settings > Features). Turned off, the page and the API
answer 404 and the log is no longer read.

## API

`GET /api/games?hours=24` (1 to 168) answers:

- `launchers`: per launcher `lookups`, `dns_seats_max`, `traffic_bytes`, `traffic_seats`,
  `cache_hit_bytes` and `cache_miss_bytes` (`null` where a source has nothing);
- `games`: the gaming services from `FLOWS_SERVICES`;
- `other_caches`: caches no launcher owns (Windows Update, drivers);
- `cache`: the hourly series, totals, hit ratio, and the last read or error;
- `sources`: which of the three sources had data.

Anyone who may see the floor plan may read it.
