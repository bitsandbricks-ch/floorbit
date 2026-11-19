# States

The state machines behind the colours on the plan and the pages. The agent's own states (connected,
away, primary, standby) are on [how-agent.md](how-agent.md).

## Switch status

Code: [`integrations/monitor.py`](../integrations/monitor.py). Every `STATUS_MONITOR_INTERVAL`
seconds (60) it asks the monitoring source for every device in one request and matches them to the
switches on the plan.

```mermaid
stateDiagram-v2
  [*] --> Baseline: first poll after a start,<br/>or after the source came back
  Baseline --> Online: device status 1
  Baseline --> Offline: device status 0
  Baseline --> Unknown: not found, disabled or ignored
  Online --> Offline: seen STATUS_MONITOR_CONFIRM (2) polls in a row
  Offline --> Online: seen 2 polls in a row
  Online --> Unknown: seen 2 polls in a row
  Unknown --> Online: seen 2 polls in a row
  Offline --> Unknown: seen 2 polls in a row
  Unknown --> Offline: seen 2 polls in a row
```

The baseline poll publishes nothing, so a restart doesn't page anyone. Each confirmed change
publishes `switch.status` ([how-integrations.md](how-integrations.md)).

## The monitoring source

Code: [`floorbit/sources/__init__.py`](../floorbit/sources/__init__.py).

```mermaid
stateDiagram-v2
  [*] --> NeverAnswered: fresh start
  NeverAnswered --> Ok: first answer
  NeverAnswered: Problems says "has not answered yet" (setup to do)
  Ok --> Offline: a poll fails<br/>(monitoring.offline, once)
  Offline --> Ok: a poll answers<br/>(monitoring.online, baseline again)
  Offline: pages answer from the last good data, marked stale
  Offline: no switch is compared, so no "switch down" flood
```

On a hosted Floorbit the source is the agent, and the alert says "The local agent is away".

## Seat on the plan

Code: [`floorbit/seat_view.py`](../floorbit/seat_view.py). The port watch reads every port of the
placed, online switches every 120 s; the seat's port comes from a cable, a learned port or the port
description ([how-seat-mapping.md](how-seat-mapping.md#who-reads-the-seats-port)).

```mermaid
flowchart TD
  s["Seat"] --> fresh{"Last port read younger<br/>than 3 port-watch rounds?"}
  fresh -- no --> u["unknown"]
  fresh -- yes --> known{"Port known and up?"}
  known -- "up" --> on["online"]
  known -- "known, down" --> off["offline"]
  known -- "port not known" --> u
```

Flags on top: `checked_in`, `taken` (the mapping has a player), `problems` (open incidents and port
trouble), `match` and `note`.

## Check-in port lookup

Code: [`integrations/checkin.py`](../integrations/checkin.py) (`wired`).

```mermaid
stateDiagram-v2
  [*] --> pending: PC through the front door
  [*] --> not_wired: phone or tablet,<br/>or no address (not through the front door)
  pending --> verified: on one access port,<br/>at most 4 MACs on it
  pending --> unverified: not found in 15 min
  unverified --> pending: crew "look for the port again"
  verified --> [*]
  verified: with a PIN, the seat learns the port
```

## Service health

Code: [`floorbit/health.py`](../floorbit/health.py). Every `HEALTH_INTERVAL` (30 s) each health plugin
is asked; a new status counts once seen `HEALTH_CONFIRM` (2) polls in a row, after a baseline poll
that publishes nothing. Then `health.changed` goes out.

```mermaid
stateDiagram-v2
  [*] --> unknown
  unknown --> up
  unknown --> warn
  unknown --> down
  up --> warn
  warn --> down
  down --> up
  up --> down
  warn --> up
  down --> warn
```

## Incidents

Code: [`floorbit/incidents.py`](../floorbit/incidents.py). Statuses are `open`, `assigned` and
`fixed`; the crew can set any of them. With automatic dispatch on, a new incident goes to the
nearest free tech ([dispatch.md](dispatch.md)).

```mermaid
stateDiagram-v2
  [*] --> open: filed (seat helpdesk, crew)
  open --> assigned: a tech takes it, or dispatch
  assigned --> fixed
  open --> fixed
  fixed --> open: reopened
```

## Public status page

Code: [`floorbit/status_page.py`](../floorbit/status_page.py).

```mermaid
flowchart TD
  hand{"Crew set a state by hand?"} -- yes --> manual["That state<br/>(operational, degraded, outage, maintenance)"]
  hand -- no --> src{"Monitoring source answers?"}
  src -- no --> unk["unknown"]
  src -- yes --> core{"A router or firewall down,<br/>or half the switches or more?"}
  core -- yes --> outage["outage"]
  core -- no --> some{"Any switch down?"}
  some -- yes --> deg["degraded"]
  some -- no --> ok["operational"]
```

## A telemetry device

```mermaid
stateDiagram-v2
  [*] --> NeverHeard
  NeverHeard --> Heard: first point
  Heard --> Silent: nothing for a few minutes
  Silent --> Heard: sends again ("back" in the agent log)
  Heard --> Heard: problem kind set while errors come,<br/>cleared after 3 min without one
```
