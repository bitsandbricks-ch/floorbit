# Traffic insights (NetFlow and IPFIX)

The **Traffic** widget (on the ready-made Traffic dashboard, `/dashboards/traffic`) shows what the hall's traffic is made of: gaming, streaming,
downloads, updates, web and other, for the whole hall and per seat block, the services most seats
use, and things ops should look at. It stays aggregate: nobody can see what a person visited.

Code: [`floorbit/flows/`](../floorbit/flows/) (parsing, classifying, aggregating, the collector),
[`floorbit/blueprints/flows.py`](../floorbit/blueprints/flows.py), [`frontend/src/pages/Traffic.tsx`](../frontend/src/pages/Traffic.tsx).

## Setting it up

On a hosted Floorbit, the [local agent](agent.md#traffic-netflow-through-the-agent) collects the
flows on the event network and sends only the summary.

The collector is its own optional container, so installs without NetFlow keep working as before:

```sh
docker compose --profile flows up -d
```

It listens on udp/2055 (`FLOWS_PORT`) for **NetFlow v5**, **NetFlow v9** and **IPFIX**, from any
number of exporters. Point the switches, the router or the firewall at the Floorbit host. Seats are
recognised by their IP address from the [seat sources](seat-mapping.md), so flows must carry the
players' own addresses: export where the seats are not behind NAT yet (the access or distribution
layer, or the inside interface of the firewall).

Anyone on the event network can send UDP to the collector, and a made-up packet would add made-up
traffic to a seat. Set `FLOWS_ALLOW` to the exporters' addresses (or their management network) and
packets from anyone else are dropped and counted (`refused` in the summary). Unset, every sender
counts, as before. On a local agent the setting goes into the agent's environment.

TODO: ask Mike which devices export flows at the event (switches, router or firewall) and in which
format, and add a tested example for each here.

The agent sends its summary every 10 seconds, and Floorbit keeps the latest one in its database
(`flows-summary.json` of the event), where every worker and pod reads it. The page says when no
agent has sent anything for 5 minutes, and when the last summary is more than a minute old.

## What it shows

| Part | What | Who sees it |
| --- | --- | --- |
| The whole hall | bytes per category, last hour and last 24 hours | everyone with `floorplan.view` |
| Per area | the same per seat block, last hour | everyone |
| Applications | per service, 24 hours: how many different seats used it, bytes down (to the seats) and up, bytes per hour for the last 6 hours, and bytes per seat block. Click one for its blocks and hours | everyone |
| Network owners | per remote network (AS) and its owner, 24 hours: how many different seats used it, bytes down and up | everyone |
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

**Network owners** come from the [iptoasn.com](https://iptoasn.com/) list
(`ip2asn-combined.tsv.gz`, public domain under PDDL 1.0), which maps address ranges to the network
(AS number) that announces them and its owner. The collector on the agent fetches it once a day into
`FLOWS_DIR`, keeps the last good copy when a fetch fails (it tries again after an hour), and looks up
each flow's remote address in memory. Private and documentation addresses have no owner. Nothing to
set up; until the first list is in, the table says so.

**HTTPS by name** (#1600). NetFlow and IPFIX carry addresses and ports, not host names, and the
exporters the events use (pfSense, Nexus) don't add the TLS server name either. So most launcher and
game downloads would only say "Web". The agent fills that gap from DNS: when a seat looks up
`cdn.example.com` and gets `198.51.100.7`, its flows to that address count for `example.com`, and so
for the [application](applications.md) whose site that is. In order:

1. The event's `FLOWS_SERVICES` and the applications' address ranges.
2. An application's or the event's own port, for the flow's remote port.
3. **The site the seat looked up**, for the answer's TTL, at least 2 and at most 30 minutes.
4. Else the site **anyone** was last given that address for, when exactly one site has it. A shared
   CDN address that answers for several sites names nobody.
5. The built-in ports ("Web" for 443).

It needs a DNS plugin whose lookups carry the answer: **AdGuard Home** does; Pi-hole's API doesn't
give the answer's addresses, so with Pi-hole flows are named by address and port only. The agent
reads the answers where it reads the lookups for [DNS analytics](dns.md), once a minute, so a
download that starts in the same minute as its lookup may count as "Web" until the next read.

Limits: nothing to match when the seat asks another resolver (DNS over HTTPS in the browser, a
hard-coded `8.8.8.8`) or connects to an address it never looked up; a connection that began before
the window keeps its name only while the address-wide match holds. Encrypted Client Hello doesn't
matter here: the lookup still went to the event's resolver.

## Privacy

Flows are personal data under Swiss and EU rules (an address at a seat is a person). So:

- A **service is only named once `FLOWS_MIN_SEATS` (5) different seats used it**. Below that it
  counts as "other", so a rare service can't point at one person. The same floor holds for a seat
  block: a service's bytes in a block are only shown when that many of the block's seats used it;
  the rest shows as "blocks with fewer seats".
- A **network owner** follows the same rule: named once 5 different seats used it, otherwise counted
  as "owners fewer seats used". Only the owner's name and AS number leave the agent, never addresses.
- **Names from DNS** are matched on the agent, in memory: which seat looked up which site and got
  which address never leaves the hall and is never written to disk. The flows they name count under
  the same five-seat rule.
- **Per seat** there is only the volume and the category mix ("80 GB, mostly gaming"), for spotting
  problems. Never services, addresses or ports on the everyday pages.
- **Raw flows** (`FLOWS_DIR/raw/`, one gzip file per hour) are kept for `FLOWS_RETENTION_DAYS` (7)
  for looking into an incident afterwards (the [flow lookup](#flow-lookup): a reasoned,
  audit-logged search), then deleted; when the agent's disk budget is used up the
  oldest go first ([agent](agent.md#the-agents-disk-budget)). `FLOWS_KEEP_RAW=false` keeps none.
- **Raw flows are merged per minute** before they are written: one line per minute and
  conversation (source, destination, protocol, ports) with the bytes, packets and how many records
  it was made of, `[minute, src, dst, proto, sport, dport, bytes, packets, records]`. Exporters
  report a long download again every active timeout, so this answers "who talked to what, when" the
  same with fewer lines. A minute is written 60 seconds after it ends, so late records still merge
  into it. With made-up traffic it took about 13 instead of 31 bytes per flow record on disk; real
  halls will differ.
- **Per-seat numbers** live only in the collector's memory and are gone after the retention too
  (or when it restarts).
- **What stays** after that is `FLOWS_DIR/hourly.jsonl`: per hour, the hall, area and service
  totals, services and network owners only with enough seats. No seats and no addresses.

`FLOWS_DIR` defaults to `flows/` next to `data.json` (`/app/state/flows` in Docker).

## Flow lookup

**Traffic › Flow lookup** (`/flow-lookup`, #1481 C) is for an incident: a P2P flood, a DDoS-like
burst, an abuse report about an address. It searches the raw flows the agents keep
(`FLOWS_DIR/raw/`, `FLOWS_RETENTION_DAYS`) and the minutes not written yet, by:

- a **seat** (its addresses from the seat sources) or an **address**: its flows both ways;
- a **destination**: an address, a network (`198.51.100.0/24`) or an owner's AS number (`AS64496`);
- a **port**: `udp/6881-6889`, `tcp/443` or `443` for both;
- a **time**: the last 15 minutes, hour, 6 hours, 24 hours or 7 days.

It needs at least one of seat, address, destination or port, never the whole hall. Each agent
answers its newest 500 matches with the totals of all of them (bytes, how many different addresses a
seat talked to), each row with its owner and application. An agent stops reading after 10 seconds
and says so: then pick a shorter time.

- **Who:** `traffic.investigate`, Admin and Lead by default ([auth.md](auth.md)).
- **Why:** every search needs a reason. It goes to the audit log with what was searched, **before**
  the agents are asked, so a search that fails is logged too. **Download CSV** is logged again, as
  an export.
- **What stays:** nothing. Floorbit shows the answer and forgets it; the raw flows stay on the agent
  and go after their retention as before.

`POST /api/traffic/lookup` `{seat, source, destination, ports, window | since + until, reason, csv}`
answers `{rows, total, bytes, peers, stopped, agents}`; the agent part is the netflow-relay plugin's
`lookup` call (`floorbit/flows/lookup.py`).

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
| `FLOWS_ALLOW` | | exporters that may send, addresses and networks, comma-separated; unset: everyone |
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
