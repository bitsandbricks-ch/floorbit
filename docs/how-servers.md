# Servers and services

How Floorbit watches what the players need besides the switches: internet lines, DNS resolvers,
internet sites, the LAN cache, game servers, and everything a health plugin reports. Every probe
runs on the agent, from the event network.

Code: [`floorbit/services.py`](../floorbit/services.py), [`floorbit/probes.py`](../floorbit/probes.py),
[`floorbit/game_servers.py`](../floorbit/game_servers.py), [`floorbit/game_query.py`](../floorbit/game_query.py),
[`floorbit/health.py`](../floorbit/health.py).

## Every 30 seconds

```mermaid
flowchart LR
  subgraph fb["Floorbit"]
    svc["Services loop<br/>SERVICES_INTERVAL (30 s)"]
    gs["Game server poller<br/>GAME_INTERVAL (30 s)"]
    hw["Health watch<br/>HEALTH_INTERVAL (30 s)"]
  end
  subgraph agent["Local agent"]
    tcp["tcp_probe: a few connects<br/>to 53, 80, 443 or 853"]
    dnsp["dns_probe: one A query"]
    gq["game_query: A2S, Minecraft or TCP"]
    hf["health_feeds: every health plugin<br/>(HTTP check, your own)"]
    mon["Monitoring source:<br/>uplink port state and traffic"]
  end
  svc -- "uplink probe host, sites" --> tcp
  svc -- resolvers --> dnsp
  svc -- "uplink port" --> mon
  gs --> gq
  hw --> hf
  tcp & dnsp & mon --> svcres["Latency, loss, answer code,<br/>traffic against capacity<br/>(last 60 samples)"]
  gq --> gsres["Up or down, players, map,<br/>player history"]
  svcres --> wall["Service health wall"]
  gsres --> wall
  hf --> wall
  lc["LAN cache log and disk"] --> wall
  fw["Firewalls"] --> wall
  wall --> conf{"New colour seen<br/>HEALTH_CONFIRM (2) times?"}
  conf -- yes --> ev["health.changed:<br/>browsers, Discord on red,<br/>webhooks, plugin hooks"]
```

A probe only connects to 53, 80, 443 or 853 and sends nothing, or one DNS query, so it can't be used
to talk to a service. Link-local addresses are never probed, and `PROBE_NETS` (`FLOORBIT_AGENT_PROBE_NETS`
on the agent) narrows where probes may go.

## RCON

```mermaid
sequenceDiagram
  autonumber
  actor Tech as Tech (games.rcon)
  participant F as Floorbit
  participant V as Vault
  participant A as Agent
  participant G as Game server
  Tech->>F: command on the RCON console
  F->>F: stops, map changes and kicks need confirm
  F->>V: open the sealed RCON password for this one command
  F->>A: call game_rcon with the address, the password and the command
  A->>G: RCON
  G-->>A: reply
  A-->>F: reply
  F->>F: audit log (a password-setting command by its name only)
  F-->>Tech: reply
```
