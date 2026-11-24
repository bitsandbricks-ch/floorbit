# Agent communication

How Floorbit and the [local agent](agent.md) talk. The agent always opens the connection, out to
Floorbit over HTTPS; nothing in the hall has to be reachable from outside. The rules and every
endpoint are in [agent.md](agent.md#the-protocol) and [agent-plugins.md](agent-plugins.md#how-it-travels).

Code: [`floorbit/agent_link.py`](../floorbit/agent_link.py) and
[`floorbit/blueprints/agent.py`](../floorbit/blueprints/agent.py) on the Floorbit side; the agent
in [bitsandbricks-ch/floorbit-agent](https://github.com/bitsandbricks-ch/floorbit-agent)
(`floorbit_agent/__init__.py`, `plugin_host.py`, `spool.py`).

## Starting up

```mermaid
sequenceDiagram
  autonumber
  participant A as Agent
  participant F as Floorbit
  A->>F: GET /api/agent/v1/hello<br/>Floorbit-Agent-Key, -Signature, -Version, -Protocol
  opt no key pinned yet, or its client cert ends within 30 days
    A->>F: POST /api/agent/v1/identity (CSR of its own key)
    F-->>A: client certificate; the key is pinned
  end
  alt key wrong or revoked
    F-->>A: 401
    Note over A: stops with exit code 1<br/>(enrol again)
  else protocol not spoken here
    F-->>A: 426 + the protocol Floorbit speaks
    Note over A: stops with exit code 1<br/>(update one side)
  else ok
    F-->>A: name, server_version, encodings,<br/>protocol, protocols, link
  end
  A->>F: GET /api/agent/v1/plugins (ETag)
  F-->>A: plugin settings (secrets too, over TLS),<br/>bundles to fetch
  A->>A: start its plugins (LibreNMS, Telemetry,<br/>syslog, front door, ...)
  alt protocols lists 2
    A->>F: GET /api/agent/v2/link (WebSocket upgrade)
    F-->>A: {"type": "hello", "name", "protocol"}
  else WebSocket blocked on the way
    Note over A: falls back to the long poll,<br/>tries the link again later
  end
```

When Floorbit can't be reached the agent waits 1 s, then 2, 4 and so on up to a minute between
tries.

## Calls: Floorbit asks, the agent answers

A page, a background loop or a crew action needs something from the hall (which switches are up,
which port an IP is on, a port bounce). Only the methods in `agent_link.METHODS` can be asked.

```mermaid
sequenceDiagram
  autonumber
  participant P as Page or loop
  participant T as Tunnel (agent_link)
  participant A as Agent
  participant L as Hall (LibreNMS, switch, ...)
  P->>T: call(method, args), waits up to 8 s
  alt no agent asked for work recently
    T-->>P: AgentUnavailable at once
    Note over P: answers from the last good data,<br/>marked stale with its age
  else agent connected
    T->>A: link: {"type": "calls"} (or the next long poll)
    A->>L: run it, up to 4 calls side by side
    L-->>A: result
    A->>T: link: {"type": "answers"} (or POST /answers)
    T-->>P: result
  end
```

With several Floorbit pods (`FLOORBIT_CLUSTER=redis`), a call made on a pod that doesn't hold the
agent's link goes to the pod that does through a Redis list, and the answer comes back the same way
([kubernetes.md](kubernetes.md)).

## Sends: the agent pushes

What the agent collects by itself goes the other way, as HTTPS posts, never over the link.

```mermaid
flowchart LR
  subgraph agent["Agent"]
    p["Agent plugin<br/>ctx.send(kind, payload)"] --> chk{"kind listed under sends:<br/>and passes its privacy rule?"}
    chk -- no --> refuse["Refused at once"]
    chk -- yes --> spool[("Spool on disk<br/>256 MB, 24 h per plugin")]
    sys["Syslog relay"] --> sq[("Syslog backlog")]
    flo["Flow collector"] --> snap["Summary"]
  end
  spool -- "POST /api/agent/v1/plugins/#lt;id#gt;/#lt;kind#gt;<br/>gzipped" --> hp["Hosted part:<br/>Plugin.agent_#lt;kind#gt;()"]
  sq -- "POST /api/agent/v1/syslog<br/>up to 2,000 lines" --> slog["Syslog page"]
  snap -- "POST /api/agent/v1/flows" --> traffic["Traffic page"]
  rep["Report every 30 s"] -- "link, or POST /api/agent/v1/report" --> page["Local agents page"]
```

A send the uplink couldn't take waits in the spool, so an outage loses nothing within those limits.

## Settings and actions

```mermaid
flowchart LR
  admin["Admin changes a plugin<br/>(Settings > Plugins, inventory)"] --> rel["reload_agents()"]
  rel -- "call: plugins_reload" --> ag["Agent"]
  ag -- "GET /api/agent/v1/plugins<br/>every minute and on reload" --> cfg["Settings for this agent<br/>(halls, plugins it leaves off)"]
  cfg --> ag
  crew["Crew runs a plugin action<br/>(role checked, audited)"] -- "call: plugin [id, action, name, args]" --> ag
  ag -- "only when the hall said yes" --> dev["Device"]
```

## Two agents in one hall

Agents for the same halls share virtual IPs with VRRP. Only the **primary** polls devices and logs in
to them; both answer Floorbit's calls and take syslog, NetFlow and traps sent to their address.

```mermaid
stateDiagram-v2
  [*] --> Standby
  Standby --> Primary: holds the first VIP
  Primary --> Standby: loses the first VIP
  Primary --> SplitBrain: VRRP between the agents drops,<br/>both take every VIP
  SplitBrain --> Standby: Floorbit's hint, the others stand by
  SplitBrain --> Primary: smallest id stays primary
```

## When the agent goes away

```mermaid
stateDiagram-v2
  [*] --> Connected: asks for work / link open
  Connected --> Suspect: on the link, silent 3 s with a call waiting
  Suspect --> Connected: answers the ping
  Suspect --> Away: no answer within 5 s, link closed
  Connected --> Away: link closed, or on the long poll<br/>a call untaken 5 s and no ask in 10 s
  Connected --> Away: no ask for 60 s
  Away --> Connected: asks again
  Away: Calls fail at once
  Away: pages show last good data, stale
  Away: one "local agent is away" alert
```

Calls that were with the agent when it went fail with "went away before it answered; it may have
run", so a port action is looked at before it is tried again.
