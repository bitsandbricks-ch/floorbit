# Local agent (hosted Floorbit)

Floorbit normally runs on the event network, next to LibreNMS and NetBox. A **hosted** Floorbit
runs somewhere else, such as a server on the internet, and can't reach them: they sit behind the
event's firewall. The **local agent** closes that gap ([issue #2](https://github.com/bitsandbricks-ch/floorbit/issues/2)).

The agent runs on the event network and opens the connection itself, out to the hosted Floorbit
over HTTPS. Nothing on the event network has to be reachable from outside, and no port has to be
opened. The hosted Floorbit hands the agent its LibreNMS questions (which switches are up, which
port an IP is on, a port's traffic). The agent asks the event's own LibreNMS and sends the answers back.

## Enrolling an agent

**Settings > Local agents** (`/settings/agents`): give the agent a name, such as the event or the
site, and press **Enrol**. An admin enrols the agent and gets its **key**, `fba_<id>_<secret>`. The key is shown once; Floorbit
keeps only a hash of it (in `data.json`, under `agents`). Give the key to the agent as `FLOORBIT_AGENT_KEY`, never in a file anyone can read. The page shows
the `docker run` line to start the agent with it.

The page lists every agent: **Connected** or not, when it was last seen, its version, and who
enrolled it when. It updates every 10 seconds. For the last hour it also shows how many calls the
agent answered, how long it took (the median, from handing a call out to getting its answer), how
many failed, and the last error with its method. A slow LibreNMS or one that refuses the agent's
token shows up there first. These numbers are kept in memory, so a restart starts them over. An agent older than the hosted
Floorbit gets an **Update** badge: pull the new image and start it again (below). An agent that
sends no version, or one Floorbit can't read, is never flagged.

Revoking the agent stops it at its next request: it has to be enrolled again with a new key. Up to
10 agents can be enrolled. Enrolling and revoking are written to the [audit log](audit.md).

While at least one agent is enrolled, the hosted Floorbit asks the agent instead of its own
monitoring plugin. Revoke every agent to go back to the plugins.

### Several agents

Every agent answers for every hall until you say otherwise. Several agents for the same hall share
the work: whichever asks first gets the next call, which suits a spare on another box for when the
first one goes down. An answer is only taken from the agent that took the call.

**An agent per hall or site.** With more than one hall, each agent has an **Answers for** field on
the page: pick the halls whose switches it can reach (empty means every hall). Once any agent is
limited like that:

- a question about one switch (its status, ports, port traffic) goes to an agent for that switch's
  hall, matched by the switch's name in the [inventory](inventory.md). A switch Floorbit doesn't know
  goes to any agent;
- a question about everything (the device list, which switch an IP is on, ARP) goes to every
  connected agent, and their answers are put together: the device lists are joined, and the first
  agent that knows an IP answers;
- each agent's inventory and cable plugins are synced under their own id (`netbox.<agent id>`, shown as
  "NetBox, Hall 2 agent"), so two sites' NetBox servers don't mark each other's devices as gone.

Changing an agent's halls is written to the [audit log](audit.md).

## Running the agent

The agent is the Floorbit image with another command, `python -m floorbit.agent`. Run it on the
event network, where it can reach LibreNMS and NetBox. It needs no Redis, no port and no domain.

**With Docker Compose** (the repository has a file for it):

```sh
cp agent.env.example agent.env     # fill in FLOORBIT_URL, FLOORBIT_AGENT_KEY, LibreNMS, NetBox
chmod 600 agent.env
docker compose -f docker-compose.agent.yml up -d
docker compose -f docker-compose.agent.yml logs -f    # "[agent] connected to … as …"
```

**With `docker run`**, as the **Local agents** page shows it:

```sh
docker run -d --restart on-failure:3 --name floorbit-agent \
  -e FLOORBIT_URL=https://floor.example.com \
  -e FLOORBIT_AGENT_KEY=fba_… \
  -e LIBRENMS_URL=https://librenms.example.com -e LIBRENMS_TOKEN=… \
  ghcr.io/bitsandbricks-ch/floorbit python -m floorbit.agent
```

**Check the setup first.** `check` tries each part once (the hosted Floorbit and the key, the
monitoring plugin, the inventory plugins), says which works and which doesn't, and exits with 0 when
everything works, 1 when something doesn't:

```sh
docker compose -f docker-compose.agent.yml run --rm agent python -m floorbit.agent check
```

```text
OK   https://floor.example.com accepts the key: this is "Spring LAN, hall 2" (Floorbit 0.1.0)
OK   the monitoring plugin answers: 24 devices
FAIL NetBox: Set the NetBox URL and API token under Settings > NetBox first. (NETBOX_URL and NETBOX_TOKEN are not set)
Fix what failed, then run the check again.
```

Set up the event's plugins on it the usual way (for LibreNMS `LIBRENMS_URL` and `LIBRENMS_TOKEN`,
for NetBox `NETBOX_URL` and `NETBOX_TOKEN`), and tell it where the hosted Floorbit is:

| Setting | What |
| --- | --- |
| `FLOORBIT_URL` | the hosted Floorbit, `https://…` |
| `FLOORBIT_AGENT_KEY` | the key from **Settings > Local agents** |
| `FLOORBIT_AGENT_INSECURE` | `1` allows an `http://` URL, for a test on a trusted network only: the key and the event data go over it |
| `FLOORBIT_DATA_FILE` | the agent's own settings file (in the image `/app/state/data.json`, elsewhere `agent-data.json` in its working directory). It keeps no floor plan |

The agent only makes outgoing requests; nothing listens on it. It runs up to 4 calls side by side,
so one slow port lookup doesn't hold up the floor plan. When the hosted Floorbit can't be reached,
it tries again after 1 second, then 2, 4 and so on, up to a minute between tries, and logs each
try. When the key is refused (wrong or revoked), it stops with exit code 1: enrol it again and
start it with the new key. That's why the Compose file restarts it only on failure, at most 3
times, instead of `unless-stopped`.

To update the agent, pull the new image and start it again (`docker compose -f
docker-compose.agent.yml pull && docker compose -f docker-compose.agent.yml up -d`). The
**Local agents** page shows each agent's version.

## The inventory through the agent

Set up the event's inventory plugin on the agent too (for NetBox: `NETBOX_URL` and
`NETBOX_TOKEN`). An inventory sync on the hosted Floorbit (**Inventory > Sync**, or **Sync
switches** in the editor) then also asks the agent: it runs each inventory plugin that is on there
and sends back their devices. They are merged under the plugin's own id (`netbox`), the same as a
local install would, so a hall that moves from a local Floorbit to a hosted one keeps its devices,
their positions and the fields you edited by hand.

The inventory page lists the agent's plugins as, for example, "NetBox (local agent)", with their last
sync. A plugin that fails on the agent fails on its own; the others still sync. If the agent is away,
the sync says so and nothing changes. A sync waits up to 25 seconds for the agent.

A plugin the agent feeds is not asked on the hosted Floorbit itself, which can't reach it anyway.

## Cables through the agent

**Cables > Import from NetBox** works the same way: the agent sends the cables of each plugin there
that knows them (NetBox), and they replace the last import as usual. A plugin the agent answered for
isn't asked on the hosted Floorbit too. The cable page lists "Local agent" among its sources.

## When the agent is away

An agent counts as **connected** while it asked for work in the last 60 seconds. A page that needs
LibreNMS waits up to 8 seconds for the agent's answer. If the agent is not connected or doesn't
answer in time, Floorbit answers from the last good data it has, marked as stale with its age, as
it does when a local LibreNMS stops answering ([offline mode](offline.md)). Switches it knows
nothing about show as unknown.

When the agent goes away, the status monitor sends one alert, as for a LibreNMS that stops
answering, but it names the agent: "The local agent is away", with when it was last heard, on
[Discord](integrations.md), in the [timeline](timeline.md) and as a `monitoring.offline` webhook with
`"agent": true` and `last_seen`. One more when it is back.

## The protocol

The agent sends its key in the `Floorbit-Agent-Key` header and its version in
`Floorbit-Agent-Version`. It needs no account and no session.

| Request | What |
| --- | --- |
| `GET /api/agent/v1/hello` | checks the key: `{"name", "server_version"}`, or 401 |
| `GET /api/agent/v1/calls?wait=25` | the calls waiting for the agent, `{"calls": [{"id", "method", "args"}]}`; waits up to `wait` seconds (at most 25) for the first one |
| `POST /api/agent/v1/answers` | `{"answers": [{"id", "ok", "result", "error"}]}`; `{"taken": n}` says how many were still awaited |

The methods are those of the monitoring source (see [architecture.md](architecture.md#inventory-and-data-sources)):
`configured`, `devices`, `device_details`, `resolve_ip`, `port_stats`, `device_ports` and `arp`, plus
`inventory_feeds`, which answers `[{"plugin", "name", "items"}]` (or `"error"` instead of `"items"`) for each
inventory plugin that's on, and `cable_feeds`, the same for each plugin that knows cables. Nothing else can be asked. The agent answers with what its own monitoring plugin returns.

For admins (**Manage settings**):

| Request | What |
| --- | --- |
| `GET /api/agents` | the enrolled agents (name, when made and by whom, last seen, version, connected, `outdated`, and `stats`: the last hour's `calls`, `failed`, `median_ms` and `last_error`), and `server_version` |
| `POST /api/agents` | `{"name"}`: enrol one. The answer holds `key`, this once |
| `PATCH /api/agents/<id>` | `{"halls": [ids]}`: the halls it answers for, empty for every hall |
| `DELETE /api/agents/<id>` | revoke it |

API tokens can't reach `/api/agents`, so a leaked token can't enrol an agent.
