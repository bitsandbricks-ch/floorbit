# Telemetry processing

From a switch's counters to the floor plan and the history. Setup and every option are in
[telemetry.md](telemetry.md); this page draws the path. The local agent is the collector: it runs
Telegraf, keeps the live picture and sends Floorbit only the normalised series and the sightings.

Code: [`floorbit/telemetry/`](../floorbit/telemetry/) (targets, Telegraf config, line protocol,
state, storage, problems) and the Telemetry plugin
[`floorbit/builtin_plugins/telemetry/`](../floorbit/builtin_plugins/telemetry/) (`agent.py` runs on
the agent, `plugin.py` on Floorbit).

## The path of a point

```mermaid
flowchart TD
  subgraph fb1["Floorbit"]
    inv["Inventory devices with the<br/>Telemetry feature on,<br/>their stored logins"] --> tg["targets.py:<br/>one target per device,<br/>drivers per device"]
  end
  tg -- "agent_settings(), pulled<br/>by the agent every minute" --> conf
  subgraph agent["Local agent"]
    conf["telegraf.py writes telegraf.conf,<br/>SIGHUP on change"] --> tel["Telegraf (supervisor.py)"]
    tel -- "SNMP poll: ports 30 s,<br/>ARP, MAC tables, LLDP/CDP 60 s" --> dev["Switches, routers,<br/>firewalls"]
    dev -- "traps, gNMI, MDT dial-out" --> tel
    pol["pollers.py every 60 s:<br/>NX-API, RESTCONF, OPNsense"] --> dev
    tel -- "line protocol, POST /write<br/>(ingest token)" --> lp["lineproto.py:<br/>parse, skip bad lines"]
    pol --> st
    lp --> st["state.py: latest picture<br/>per device, in memory"]
    tel -- "its own log lines" --> pr["problems.py:<br/>no answer, refused login, ..."]
    st --> snap["Every 60 s: snapshot()<br/>normalised series"]
    st --> sight["Every 60 s: clients.sightings()<br/>MAC on access port + IPs"]
  end
  snap -- "send 'series'" --> sto
  sight -- "send 'endpoints'" --> eh
  subgraph fb2["Floorbit"]
    sto["storage.sample()"] --> vm[("VictoriaMetrics, when set")]
    sto --> lite[("Lite: Floorbit's database<br/>1 min for 6 h, 15 min for 2 days")]
    eh[("IP/MAC history<br/>floorbit_endpoints, 7 days")]
  end
```

MAC tables, ARP and neighbours stay in the agent's memory: they name the people at the seats, so
they are never stored as series ([telemetry.md](telemetry.md#privacy)). What leaves the agent is
the normalised numbers and the sightings for the [IP/MAC history](endpoints.md). Raw points don't
reach VictoriaMetrics on this path ([#955](https://github.com/bitsandbricks-ch/floorbit/issues/955)).

## Reading the live picture

Pages that need the live picture don't read storage. They ask the monitoring source, which reaches
the agent's in-memory state through the link.

```mermaid
sequenceDiagram
  participant P as Floor plan, check-in, topology
  participant S as sources.monitoring()
  participant A as Agent
  participant M as Agent's monitoring plugin
  P->>S: device_ports(sw-a-01), resolve_ip(ip), neighbours()
  S->>A: call over the link
  A->>M: LibreNMS if set up, else Telemetry (id order)
  M-->>A: from state.py (Telemetry) or the LibreNMS API
  A-->>S: answer
  S-->>P: answer, or the last good one marked stale
```

## When a device sends nothing

```mermaid
flowchart TD
  line["Telegraf error line<br/>E! [inputs.snmp::sw-01] ..."] --> kind{"Sort into a kind"}
  perr["API poller error"] --> kind
  kind --> k1["Nothing listens"]
  kind --> k2["No answer<br/>(also a wrong SNMP community)"]
  kind --> k3["Refused the login<br/>(not tried again until cleared)"]
  kind --> k4["No route"]
  kind --> k5["TLS failed"]
  kind --> k6["Cannot open its listening port"]
  k1 & k2 & k3 & k4 & k5 & k6 --> show["Per device and collection type:<br/>Telemetry page, device's tab,<br/>agent page, agent log"]
  show --> clear{"Device sends again,<br/>or 3 min without the error?"}
  clear -- yes --> gone["Problem cleared"]
```

## Two agents

Both agents get the targets; only the primary polls and logs in. A device can be pinned to one
agent ("one agent per device"), which then polls it whatever VRRP says
([telemetry.md](telemetry.md#two-agents-for-the-same-devices)).
