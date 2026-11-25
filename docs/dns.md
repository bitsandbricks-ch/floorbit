# DNS analytics

What the hall looks up, from the event's DNS resolver: lookups per hour, the top sites, categories
(gaming, streaming, social, updates), sites that are new today and what the resolver blocked. It's
the **DNS** widget (on the ready-made Traffic dashboard) and in `GET /api/dns`.

It answers questions like "did the game's patch day reach the hall?", "is Discord down or is it
us?" and "how much does the ad blocker catch?", without telling anyone what a person looked up.

## Privacy

DNS lookups say a lot about a person, so Floorbit keeps only what the whole hall does. The rule
is the same as for [traffic](flows.md):

- **Sites, not names.** `cdn.steamcontent.com` counts as `steamcontent.com`. Local names (one
  label, `.lan`, `.local`, `.home.arpa`, reverse lookups) are dropped: they name people's machines.
- **Five seats or no name.** A site is only named once `DNS_MIN_SEATS` (5) different clients looked
  it up within the same hour. Below that its lookups count in the totals as "not named".
- **No clients.** While an hour is open, clients are counted as keyed hashes; the key only lives in
  memory, so a hash can't be matched to an address, not even after a restart. When the hour
  closes only the number of clients stays.
- **A week.** Closed hours are kept `DNS_RETENTION_HOURS` (168) in `dns.json` next to `data.json`,
  then dropped. Nothing is per seat, per person or per IP.

Turning the feature off (Settings > Plugins > Built in) stops Floorbit asking the resolver.

## Where the lookups come from

A plugin with `uses: [dns]` reads the resolver's query log and defines `dns_queries(since)`: the
lookups after that unix time.

```python
def dns_queries(self, since):
    return [{"ts": 1794652800.5, "domain": "cdn.steamcontent.com", "client": "198.51.100.10",
             "blocked": False}]
```

Floorbit asks every `DNS_INTERVAL` seconds (60) and remembers the newest `ts` per plugin, so a
plugin may answer with more than was asked and nothing is counted twice. It reads at most 50,000
lookups a poll. See [plugins.md](plugins.md) for writing one. With the demo data on
(`FLOORBIT_DEMO=1`) the demo hall looks things up too.

Two resolvers have a plugin in the Marketplace, off until turned on under Settings > Plugins:
[AdGuard Home and Pi-hole](plugins.md#in-the-marketplace) (6 and
newer). For another resolver, write a small plugin; the resolver needs a query log that
Floorbit can read over HTTP.

## What the page shows

| Part | What it is |
| --- | --- |
| Lookups, Blocked | All lookups in the time range, and how many the resolver blocked. |
| Sites named, Not named | Sites past the five-seat rule, and lookups that weren't (rare sites, local names). |
| Lookups per hour | Bars per hour, the blocked part in red. |
| Categories | Lookups per category, from the named sites. |
| Top sites | The busiest named sites, with the most seats that looked one up in an hour. |
| Most blocked | Named sites the resolver blocked most. |
| New in the last 6 hours | Named sites first seen in the last 6 hours, once there is a day of history. |

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `DNS_MIN_SEATS` | `5` | Different clients a site needs within an hour before it's named (at least 2). |
| `DNS_RETENTION_HOURS` | `168` | How long closed hours are kept. |
| `DNS_INTERVAL` | `60` | Seconds between asking the plugins (at least 15). |

## API

`GET /api/dns?hours=24` (1 to 168) answers the numbers above as JSON: `hours`, `lookups`, `blocked`,
`block_share`, `sites`, `categories`, `unnamed_lookups`, `new`, `blocked_sites`, `min_clients`,
`plugins`, `last_poll` and `error`. Anyone who may see the floor plan may read it.

On a hosted Floorbit, the [local agent](agent.md#dns-analytics-through-the-agent) reads the resolver and sends
the lookups with hashed clients and names already cut to the site.
