# Integrations

How Floorbit's parts tell each other and the outside world what happened, and how the outside
sources (NetBox, LibreNMS, syslog, NetFlow) come in. Settings and payloads are in
[integrations.md](integrations.md), [api.md](api.md#webhooks), [syslog.md](syslog.md) and
[flows.md](flows.md).

## The event bus

Code: [`integrations/events.py`](../integrations/events.py), [`floorbit/cluster.py`](../floorbit/cluster.py),
[`floorbit/webhooks.py`](../floorbit/webhooks.py), [`integrations/discord.py`](../integrations/discord.py).
Anything in the app can `publish(type, data)`; everything that reacts subscribes.

```mermaid
flowchart TD
  subgraph producers["Publishers"]
    mon["Status monitor:<br/>switch.status, monitor.poll,<br/>monitoring.offline / online"]
    hl["Health watch: health.changed"]
    ci["Check-in: checkin, checkin.verified"]
    inc["Incidents: incident.changed"]
    att["Port watch: attention.changed,<br/>seats.changed, stats.changed"]
    oth["Security, power, forecast, log alerts"]
  end
  producers --> bus{{"events.publish()"}}
  bus --> sse["SSE /api/events:<br/>every open browser, kiosk"]
  bus -- "FLOORBIT_CLUSTER=redis" --> rp["Redis pub/sub:<br/>browsers on the other pods"]
  bus --> lead{"Leader pod?<br/>(leader_only subscribers)"}
  lead -- yes --> dc["Discord: switch down/up after<br/>its cooldown, source away,<br/>health red, security, power"]
  lead -- yes --> wh["Webhooks: a small stable set<br/>(switch.down, seat.checked_in, ...)<br/>signed, retried 10 s, 1 min, 5 min"]
  lead -- yes --> tl["Timeline, replay frames,<br/>plugin hooks"]
```

Python subscribers run on the pod where the event was published. Ones that post, send or write
are `leader_only`: every pod runs the background loops, and the alert should go out once. Events
caused by a request act on the pod that took it. With Redis away, every pod acts as the leader: a
duplicate alert is better than none. Webhook payloads carry no nicks, IPs or MACs.

## Which monitoring source answers

Code: `registry.monitoring_source()` in [`floorbit/plugins/__init__.py`](../floorbit/plugins/__init__.py),
[`floorbit/sources/__init__.py`](../floorbit/sources/__init__.py).

```mermaid
flowchart TD
  call["sources.monitoring().resolve_ip(), device_ports(), devices() ..."] --> ag{"Agent link active?<br/>(always, unless the demo data<br/>stands in and no agent is enrolled)"}
  ag -- yes --> agent["Ask the agent; it runs the call on its own monitoring plugin"]
  ag -- no --> local["Ask the plugin here (demo)"]
  agent --> pick
  local --> pick["Monitoring plugins that are on:<br/>demo first, then set up before not,<br/>then id order"]
  pick --> one["The first one answers alone<br/>(librenms before telemetry)"]
  one -- "fails or times out" --> stale["Last good answer, marked stale"]
```

Only one source answers at a time. With LibreNMS and Telemetry both on and set up, LibreNMS
answers every lookup ([telemetry.md](telemetry.md#set-it-up), step 4). Picking the source per kind
of data is planned ([#945](https://github.com/bitsandbricks-ch/floorbit/issues/945)).

## NetBox and the inventory

```mermaid
sequenceDiagram
  autonumber
  participant T as Sync now, or every INVENTORY_SYNC_MINUTES (leader)
  participant F as Floorbit (blueprints/inventory.py)
  participant A as Agent
  participant N as NetBox
  T->>F: run_sync()
  F->>A: call inventory_feeds
  A->>N: devices (the agent's NetBox plugin)
  N-->>A: devices
  A-->>F: per plugin: items, or its error
  F->>F: inventory.sync(): merged under each plugin's own id,<br/>fields changed by hand are locked and kept
```

The Cables page's **Import** asks `cable_feeds` the same way: imported cables replace the last
import, and a crew cable on the same switch port wins ([cables.md](cables.md)).

## Syslog and NetFlow from the hall

```mermaid
flowchart LR
  subgraph hall["Event network"]
    devs["Switches, firewalls,<br/>DHCP server"] -- "syslog udp/5514" --> sr["Agent syslog relay<br/>(backlog on disk)"]
    exp["Exporters"] -- "NetFlow v5/v9, IPFIX<br/>udp/2055" --> fc["Agent flow collector"]
    fc -- "GET /api/agent/v1/seats<br/>seat_of, area_of" --> seatmap["IP to seat and area"]
    seatmap --> agg["Aggregate per hall and block,<br/>per seat only volume and mix"]
  end
  sr -- "POST /api/agent/v1/syslog<br/>up to 2,000 lines" --> sl["syslog.py: parse, port events,<br/>DHCP leases (IP to MAC)"]
  sl --> la["Log alerts: logs.alert"]
  sl --> lp["Syslog page"]
  sl --> vl[("VictoriaLogs or Loki plugin,<br/>when on")]
  agg -- "POST /api/agent/v1/flows<br/>snapshot" --> tr["Traffic page and widget"]
```

## Planned: LibreNMS alerts as webhooks

**Planned, not built.** From section 5 of the plan "IP/MAC lookups, table walks and telemetry
logging" (2026-11-19), issue [#951](https://github.com/bitsandbricks-ch/floorbit/issues/951). When LibreNMS runs, it becomes the source for port and device
states, and Telemetry stops its own 30 s port polling. LibreNMS polls every 5 minutes, so its alerts
are pushed instead of waited for.

```mermaid
flowchart LR
  S["Switch"] -. traps .-> AG["Agent trap listener"]
  S -. traps .-> L["LibreNMS"]
  L -. "polls every 5 min" .-> S
  L -. "alert rule fires<br/>(port down, device down, recoveries),<br/>API transport" .-> W["Agent webhook listener"]
  W -. "over the agent link" .-> F["Floorbit: Problem and<br/>port state at once"]
  AG -.-> F
  F -. "reads every poll as fallback" .-> L
```

The LibreNMS plugin settings would show the alert rules and transport to paste into LibreNMS, with
a **Send test** check. If the webhook goes quiet, the normal read still runs, so nothing is lost,
only slower.
