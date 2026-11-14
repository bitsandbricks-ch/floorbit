# Traffic insights (NetFlow and IPFIX)

**Traffic** in the top bar (`/traffic`) shows what the hall's traffic is made of: gaming, streaming,
downloads, updates, web and other, for the whole hall and per seat block, the services most seats
use, and things ops should look at. It stays aggregate: nobody can see what a person visited.

Code: [`floorbit/flows/`](../floorbit/flows/) (parsing, classifying, aggregating, the collector),
[`floorbit/blueprints/flows.py`](../floorbit/blueprints/flows.py), [`frontend/src/pages/Traffic.tsx`](../frontend/src/pages/Traffic.tsx).

## Setting it up

The collector is its own optional container, so installs without NetFlow keep working as before:

```sh
docker compose --profile flows up -d
```

It listens on udp/2055 (`FLOWS_PORT`) for **NetFlow v5**, **NetFlow v9** and **IPFIX**, from any
number of exporters. Point the switches, the router or the firewall at the Floorbit host. Seats are
recognised by their IP address from the [seat sources](seat-mapping.md), so flows must carry the
players' own addresses: export where the seats are not behind NAT yet (the access or distribution
layer, or the inside interface of the firewall).

TODO: ask Mike which devices export flows at the event (switches, router or firewall) and in which
format, and add a tested example for each here.

The collector hands its numbers to Floorbit through Redis (`floorbit:flows`), so it needs the same
Redis as the app. The page says when no collector has sent anything, and when the last summary is
more than a minute old.

## What it shows

| Part | What | Who sees it |
| --- | --- | --- |
| The whole hall | bytes per category, last hour and last 24 hours | everyone with `floorplan.view` |
| Per area | the same per seat block, last hour | everyone |
| Top services | bytes per service and how many different seats used it, 24 hours | everyone |
| Look at this | P2P or torrent floods, DDoS-like bursts, seats answering DHCP or DNS | everyone sees the kind; `seats.view` sees which seat |
| Per seat | total volume and the category mix only, 24 hours | `seats.view` |

**Services** come from rules: built-in ones for well-known ports (Steam, Battle.net, Riot Games,
Minecraft, RTMP, BitTorrent, Windows delivery optimisation, web, DNS), and the event's own rules in
`FLOWS_SERVICES`, checked first. Address ranges are what make them useful, for example the LAN
cache:

```json
[{"name": "LAN cache", "category": "downloads", "cidr": ["192.0.2.50/32"]},
 {"name": "Tournament servers", "category": "gaming", "cidr": ["198.51.100.0/28"]},
 {"name": "Some game", "category": "gaming", "ports": ["udp/7777-7780"]}]
```

**Domains and sites** (from DNS and TLS SNI) need data that NetFlow and IPFIX don't carry. TODO: ask
Mike whether the event's DNS resolver logs can be read; until then services come from addresses and
ports only.

## Privacy

Flows are personal data under Swiss and EU rules (an address at a seat is a person). So:

- A **service is only named once `FLOWS_MIN_SEATS` (5) different seats used it**. Below that it
  counts as "other", so a rare service can't point at one person.
- **Per seat** there is only the volume and the category mix ("80 GB, mostly gaming"), for spotting
  problems. Never services, addresses or ports.
- **Raw flows** (`FLOWS_DIR/raw/`, one gzip file per hour) are kept for `FLOWS_RETENTION_DAYS` (7)
  for looking into an incident afterwards, then deleted. `FLOWS_KEEP_RAW=false` keeps none.
- **Per-seat numbers** live only in the collector's memory and are gone after the retention too
  (or when it restarts).
- **What stays** after that is `FLOWS_DIR/hourly.jsonl`: per hour, the hall, area and service
  totals, services only with enough seats. No seats and no addresses.

`FLOWS_DIR` defaults to `flows/` next to `data.json` (`/app/state/flows` in Docker).

## Anomalies

| Kind | When (per minute) |
| --- | --- |
| P2P | a seat talks to `FLOWS_P2P_PEERS` (300) or more different addresses, or sends over 50 MB of BitTorrent |
| Burst | a seat sends `FLOWS_BURST_PPS` (50,000) packets per second or more, or one address gets that many from three or more seats |
| Rogue DHCP | a seat sends DHCP offers (from udp/67) |
| Rogue DNS | a seat answers DNS (from udp/53) to other seats |

An entry stays for ten minutes after it was last seen.

## Settings

| Setting | Default | |
| --- | --- | --- |
| `FLOWS_PORT` | `2055` | udp port the collector listens on |
| `FLOWS_SERVICES` | | the event's own service rules, a JSON list (above) |
| `FLOWS_MIN_SEATS` | `5` | different seats before a service is named (at least 2) |
| `FLOWS_RETENTION_DAYS` | `7` | days raw flows and per-seat numbers are kept |
| `FLOWS_KEEP_RAW` | `true` | keep raw flows at all |
| `FLOWS_DIR` | next to `data.json` | where raw flows and hourly totals go |
| `FLOWS_P2P_PEERS` | `300` | peers per minute that count as P2P |
| `FLOWS_BURST_PPS` | `50000` | packets per second that count as a burst |

## Demo

With `FLOORBIT_DEMO=1` the app makes flows for the demo hall itself (no collector): Steam matches,
the LAN cache, streams, updates, a torrent at D-5 and the rogue DHCP server at A-7 that the security
demo shows too.
