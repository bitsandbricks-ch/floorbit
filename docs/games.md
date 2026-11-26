# Game and launcher insights

What the hall plays and downloads, and how much the LAN cache saved: per launcher (Steam,
Battle.net, Riot Games, Epic Games, EA app, Ubisoft Connect, Xbox, Minecraft), the bytes the LAN
cache served for it, its traffic and its DNS lookups. It's the **Games** widget (on the ready-made
Traffic dashboard), the top of **Traffic > Games and downloads** (with the LAN cache below it,
docs/lancache.md) and in `GET /api/games`.

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

| The event's game servers | Players right now, for the game each server runs. | Settings › Game servers |

Launchers no source has seen are left out. A launcher can be in one column and not another: the
built-in traffic rules only know the ports Steam, Battle.net, Riot Games and Minecraft publish, and
the LAN cache only carries launchers that cache-domains lists.

**Games played** shows, per game, the most seats any source saw: DNS lookups of its sites, traffic to
its ports and servers, players on the event's game servers. Several Steam games share Valve's ports,
so a game's own sites and server addresses tell more than ports; a game only the LAN cache saw
shows its downloads instead.

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

The feature switch is **Game insights** (Settings > Plugins > Built in). Turned off, the page and the API
answer 404 and the log is no longer read.

## API

`GET /api/games?hours=24` (1 to 168) answers:

- `launchers`, `titles` (games) and `sitegroups`: per application `id`, `name`, `kind`, `part_of`,
  `lookups`, `dns_seats_max`, `traffic_bytes`, `traffic_seats`, `cache_hit_bytes`,
  `cache_miss_bytes`, `players` (`null` where a source has nothing) and `seats`, the most of them;
- `games`: the gaming services from `FLOWS_SERVICES`;
- `other_caches`: caches no launcher owns (Windows Update, drivers);
- `cache`: the hourly series, totals, hit ratio, and the last read or error;
- `sources`: which of the sources had data (`dns`, `traffic`, `cache`, `servers`).

Anyone who may see the floor plan may read it.
