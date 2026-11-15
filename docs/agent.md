# Local agent (hosted Floorbit)

Floorbit normally runs on the event network, next to LibreNMS and NetBox. A **hosted** Floorbit
runs somewhere else, such as a server on the internet, and can't reach them: they sit behind the
event's firewall. The **local agent** closes that gap ([issue #2](https://github.com/bitsandbricks-ch/floorbit/issues/2)).

The agent runs on the event network and opens the connection itself, out to the hosted Floorbit
over HTTPS. Nothing on the event network has to be reachable from outside, and no port has to be
opened. The hosted Floorbit hands the agent its LibreNMS questions (which switches are up, which
port an IP is on, a port's traffic). The agent asks the event's own LibreNMS and sends the answers back.

!!! note "Work in progress"
    This page describes the hosted side. The agent program itself, NetBox through the agent and
    a Compose file for it follow in the next pull requests.

## Enrolling an agent

**Settings > Local agents** (`/settings/agents`): give the agent a name, such as the event or the
site, and press **Enrol**. An admin enrols the agent and gets its **key**, `fba_<id>_<secret>`. The key is shown once; Floorbit
keeps only a hash of it (in `data.json`, under `agents`). Give the key to the agent as `FLOORBIT_AGENT_KEY`, never in a file anyone can read. The page shows
the `docker run` line to start the agent with it.

The page lists every agent: **Connected** or not, when it was last seen, its version, and who
enrolled it when. It updates every 10 seconds.

Revoking the agent stops it at its next request: it has to be enrolled again with a new key. Up to
10 agents can be enrolled. Enrolling and revoking are written to the [audit log](audit.md).

While at least one agent is enrolled, the hosted Floorbit asks the agent instead of its own
monitoring plugin. Revoke every agent to go back to the plugins.

## When the agent is away

An agent counts as **connected** while it asked for work in the last 60 seconds. A page that needs
LibreNMS waits up to 8 seconds for the agent's answer. If the agent is not connected or doesn't
answer in time, Floorbit answers from the last good data it has, marked as stale with its age, as
it does when a local LibreNMS stops answering ([offline mode](offline.md)). Switches it knows
nothing about show as unknown.

## The protocol

The agent sends its key in the `Floorbit-Agent-Key` header and its version in
`Floorbit-Agent-Version`. It needs no account and no session.

| Request | What |
| --- | --- |
| `GET /api/agent/v1/hello` | checks the key: `{"name", "server_version"}`, or 401 |
| `GET /api/agent/v1/calls?wait=25` | the calls waiting for the agent, `{"calls": [{"id", "method", "args"}]}`; waits up to `wait` seconds (at most 25) for the first one |
| `POST /api/agent/v1/answers` | `{"answers": [{"id", "ok", "result", "error"}]}`; `{"taken": n}` says how many were still awaited |

The methods are those of the monitoring source (see [architecture.md](architecture.md#inventory-and-data-sources)):
`configured`, `devices`, `device_details`, `resolve_ip`, `port_stats`, `device_ports` and `arp`. Nothing else
can be asked. The agent answers with what its own monitoring plugin returns.

For admins (**Manage settings**):

| Request | What |
| --- | --- |
| `GET /api/agents` | the enrolled agents (name, when made and by whom, last seen, version, connected) |
| `POST /api/agents` | `{"name"}`: enrol one. The answer holds `key`, this once |
| `DELETE /api/agents/<id>` | revoke it |

API tokens can't reach `/api/agents`, so a leaked token can't enrol an agent.
