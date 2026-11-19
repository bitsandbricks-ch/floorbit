# Seats, ports and MACs

How a seat gets its switch port, and from that its MAC, IP and nick. The rules are in
[seat-mapping.md](seat-mapping.md); this page draws them. The key is always **switch + port**: an IP
or MAC is only the way to find the port.

Code: [`floorbit/seatmap.py`](../floorbit/seatmap.py) (hand entries),
[`integrations/seat_sources.py`](../integrations/seat_sources.py) (the merge),
[`integrations/checkin.py`](../integrations/checkin.py) (PIN check-in and the background lookup),
[`floorbit/seat_walk.py`](../floorbit/seat_walk.py) (the crew's walk-through),
[`floorbit/cables.py`](../floorbit/cables.py) (`port_seats`).

## Where a seat's fields come from

Every seat source is asked, and the first one with a value for a field wins, field by field. A hand
entry that leaves a field empty lets the next source fill it.

```mermaid
flowchart TD
  ask["Seat mapping asked for seat A-12<br/>(GET /api/seat-map, seat inspector, search)"] --> m
  m{"1st: Hand entry on the<br/>Seat mapping page?"} -- "field set" --> win["That value wins"]
  m -- "field empty" --> p
  p{"2nd: ports: a cable to the seat,<br/>else the port a check-in or<br/>seat walk learned?"} -- "field set" --> win
  p -- "field empty" --> n
  n{"3rd: network: MAC and IP seen on<br/>that port in the last MAC/ARP read?<br/>(one machine on the port only)"} -- "field set" --> win
  n -- "field empty" --> pl
  pl{"4th: Plugins with uses: [mapping]"} -- "field set" --> win
  pl -- "field empty" --> s
  s{"5th: SEAT_SOURCES in order:<br/>json (seats.json), checkin, http"} -- "field set" --> win
  s -- "nobody knows" --> none["Field stays empty"]
```

## PIN check-in

The attendee types the PIN from the seat card and a nick on the seat PC. The page answers at once;
the port is looked up in the background.

```mermaid
sequenceDiagram
  autonumber
  participant PC as Seat PC
  participant FD as Agent front door
  participant FB as Floorbit (check_in)
  participant Q as Background verifier
  participant MON as Monitoring source (via agent)
  PC->>FD: open checkin.example.com, type PIN + nick
  FD->>FB: request + Floorbit-Client-IP + agent key
  Note over FB: IP only from the front door,<br/>never the request's own address
  FB->>FB: PIN to seat, lockout after 10 wrong PINs,<br/>one PIN per PC
  FB-->>PC: "Checked in", wired = pending<br/>(phone or no IP: not_wired)
  FB->>Q: wake
  loop every 10 s, oldest first, at most CHECKIN_VERIFY_RATE a second
    Q->>MON: resolve_ip(ip), cached 60 s
    MON-->>Q: switch, port, MAC, MACs on that port
    alt one access port with at most 4 MACs
      Q->>FB: wired = verified, port_seen = switch + port
      FB->>FB: with a PIN: learn_port(seat, port)<br/>into seat_ports.json
    else 15 minutes without an answer
      Q->>FB: wired = unverified
    end
  end
```

## How the monitoring source finds the port

`resolve_ip` is the same call for check-in, the captive portal, search and the seat walk's second
step. Which plugin answers it is picked by `registry.monitoring_source()`: the first monitoring
plugin that is on and set up, in id order, so **LibreNMS answers when it is set up, else Telemetry**
([how-integrations.md](how-integrations.md#which-monitoring-source-answers)).

```mermaid
flowchart TD
  ip["IP of the seat PC"] --> arp{"ARP table on a<br/>core or router has it?"}
  arp -- no --> none["None: not on the network yet"]
  arp -- yes --> mac["MAC"]
  mac --> fdb["Every MAC table (FDB) that holds this MAC"]
  fdb --> drop["Skip ports matching the exclude list"]
  drop --> pick["Sort: non-uplink ports first<br/>(not an LLDP/CDP neighbour, at most<br/>EDGE_PORT_MACS = 4 MACs), then fewest MACs"]
  pick --> ans["switch, port, VLAN, macs_on_port"]
```

Every switch between the core and the seat learns the MAC too, on its uplink, so the port with the
fewest MACs is the seat's. One rule says what a seat's port is: at most 4 MACs (one PC and its
VMs), `floorbit/edge_ports.py`. Check-in only counts a port as `verified` when it passes, the seat
walk refuses one that doesn't, and Telemetry, the IP/MAC history and the planned lookups treat a
port above it as an uplink.

## Crew seat walk

The crew plugs a laptop into each seat's port and presses **Locate**. Freshest answer first,
because every seat counts. Each try runs for up to 20 seconds, retrying every 3 seconds.

```mermaid
flowchart TD
  start["Locate at seat A-12"] --> ip{"Laptop's IP known?"}
  ip -- "behind NAT or hosted" --> hello["Laptop says hello through the<br/>agent with a one-time code"] --> ipok["IP on the event network"]
  ip -- yes --> ipok
  ipok --> havemac{"MAC known from<br/>the last seat?"}
  havemac -- yes --> ssh
  havemac -- no --> m1{"Monitoring mac_for_ip?"}
  m1 -- yes --> ssh
  m1 -- no --> m2{"IP/MAC history?"}
  m2 -- yes --> ssh
  m2 -- no --> m3{"SSH 'show ip arp' on<br/>the routers?"}
  m3 -- yes --> ssh
  m3 -- no --> mon
  ssh["SSH 'show mac address-table address'<br/>(when a switch login is stored)<br/>first the likely switches: last seat's,<br/>cable's, learned; then the rest, 12 at a time<br/>uplinks skipped"] --> one{"Found on one<br/>access port?"}
  one -- yes --> same1{"Same port as<br/>the last seat?"}
  same1 -- "yes: stale" --> mon
  same1 -- no --> save
  one -- no --> mon["Monitoring resolve_ip<br/>(only as fresh as its last read)"]
  mon --> same2{"Found, at most 4 MACs on it,<br/>and not the last seat's port?"}
  same2 -- yes --> save["learn_port(seat, port, source = walk)"]
  same2 -- no --> retry["Try again in 3 s,<br/>up to 20 s"]
  retry --> ipok
```

The monitoring step refuses a port with more than 4 MACs: when the access switch hasn't seen the
laptop (not polled, or its entry aged out), only an uplink still has the MAC, and that is never the
seat's port. The walk keeps the MAC and tries again.

## Who reads the seat's port

A learned or cabled port is what the rest of Floorbit uses to say "this port is that seat".

```mermaid
flowchart LR
  cab["Cables to a seat<br/>(Cables page, patch plan)"] --> ps["cables.port_seats()<br/>a cable wins"]
  lp["Learned ports<br/>seat_ports.json<br/>(PIN check-in, seat walk)"] --> ps
  ps --> watch["Port watch every 120 s<br/>(attention.py)"]
  alias["Port description (ifAlias)<br/>names the seat"] --> watch
  watch --> state["Seat online / offline<br/>on the plan and Seats view"]
  watch --> att["Needs attention:<br/>no check-in, flapping, errors"]
  watch --> sp["Status page: seats behind a switch"]
  hand["Hand entry with switch + port<br/>(Seat mapping page)"] --> src["Seat sources merge"]
  ps --> src
  src --> insp["Seat inspector, search,<br/>switch of a seat"]
```

Hand entries reach the seat sources, but not `cables.port_seats()`, so the port watch does not see
them: a seat whose port was only typed in by hand stays `unknown` on the plan ([#953](https://github.com/bitsandbricks-ch/floorbit/issues/953)).

## Planned: check-in driven lookups

**Planned, not built.** From the plan "IP/MAC lookups, table walks and telemetry logging"
(2026-11-19), issues [#945](https://github.com/bitsandbricks-ch/floorbit/issues/945) (source per kind of data), [#946](https://github.com/bitsandbricks-ch/floorbit/issues/946) (segments and an SNMP
client on the agent), [#947](https://github.com/bitsandbricks-ch/floorbit/issues/947) (this lookup) and [#949](https://github.com/bitsandbricks-ch/floorbit/issues/949) (the unassigned list). Lookups would ask the switches directly with SNMP GETs (pysnmp on the agent), narrowed
by the seat's section and block ([how-switch-placement.md](how-switch-placement.md#planned-switches-serve-blocks-and-sections)),
instead of waiting for the next table read.

```mermaid
flowchart TD
  A["Check-in: seat walk, PIN or captive portal"] -.-> B["Agent reports the PC's IP;<br/>PIN or walk names the seat"]
  B -.-> C{"IP already mapped<br/>to a switch port?"}
  C -. yes .-> R["Seat = switch + port"]
  C -. no .-> D{"Cached tables know it?<br/>LibreNMS first, then Telemetry"}
  D -. yes .-> R
  D -. no .-> E["Segment from the IP range:<br/>VLAN + IP range"]
  E -.-> F{"Segment on for lookups?<br/>(all off by default)"}
  F -. no .-> T["To-do: type the MAC or pick the port"]
  F -. yes .-> G["IP to MAC: one GET of the core's<br/>ipNetToMediaPhysAddress<br/>(skipped when the walk has the MAC)"]
  G -.-> S1["GET dot1dTpFdbPort for the MAC<br/>on the section's switches"]
  S1 -. found .-> R
  S1 -. "not found" .-> S2["... on the block's other switches"]
  S2 -. found .-> R
  S2 -. "not found" .-> S3["... on every other switch<br/>carrying that VLAN"]
  S3 -. found .-> R
  S3 -. "not found" .-> T
  R -.-> L{"Matches the switches<br/>expected for the seat?"}
  L -. yes .-> M["Saved; the learned seat<br/>feeds section suggestions"]
  L -. no .-> N["Drift shown right there,<br/>in the check-in or walk"]
  N -.-> M
  P["Every 5 min: LibreNMS tables<br/>vs the seat mapping"] -.-> U["Unassigned list: ports without a seat,<br/>IPs without a port, seats without a PC"]
```

Uplinks are skipped as today (trunk ports, LLDP/CDP neighbours, more than 4 MACs). A lookup is about
1 + 2 small GETs per switch asked, deduplicated per IP or MAC for 60 seconds.
