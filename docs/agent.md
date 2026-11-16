# Local agent (hosted Floorbit)

Floorbit normally runs on the event network, next to LibreNMS and NetBox. A **hosted** Floorbit
runs somewhere else, such as a server on the internet, and can't reach them: they sit behind the
event's firewall. The **local agent** closes that gap ([issue #2](https://github.com/bitsandbricks-ch/floorbit/issues/2)).

The agent runs on the event network and opens the connection itself, out to the hosted Floorbit
over HTTPS. Nothing on the event network has to be reachable from outside, and no port has to be
opened. The hosted Floorbit hands the agent its LibreNMS questions (which switches are up, which
port an IP is on, a port's traffic). The agent asks the event's own LibreNMS and sends the answers back.

## What works on a hosted Floorbit

The agent answers for the **monitoring** plugin (LibreNMS, or whichever monitoring plugin is on
there: Zabbix, Prometheus, UniFi, Aruba, MikroTik) and for the **inventory and cable** plugins
(NetBox). Everything built on those works as with a local install:

| Works through the agent | Asks |
| --- | --- |
| Floor plan switch status, the status monitor and its alerts, the status page | monitoring |
| Port traffic, port lists, needs attention, "which port is this seat on" | monitoring |
| Check-in and seat search (IP to switch port, ARP) | monitoring |
| Inventory sync and cable import | inventory, cables |
| The health wall's checks (HTTP check, or any health plugin turned on there) | health |
| DNS analytics (Pi-hole, AdGuard Home, turned on there) | dns |
| The Wi-Fi page (UniFi as a Wi-Fi source, turned on there): open it at `/wifi` | wifi |
| Syslog on the Logs page, when the agent listens for it (`FLOORBIT_AGENT_SYSLOG_PORT`) | syslog |
| The Traffic page (NetFlow and IPFIX), when the agent collects flows (`FLOORBIT_AGENT_FLOWS_PORT`) | traffic |

Pages that only use Floorbit's own data work anyway: seats, incidents, schedule, gear, electrics
readings typed in, tournaments, the speed test (it measures the path to the hosted server, not
inside the hall), and so on.

**Not through the agent yet.** These need the hosted Floorbit itself to reach the event network,
so on a hosted Floorbit they only work when that service is reachable from it:

| Feature | Why |
| --- | --- |
| Port actions (SSH ports), switch commands and terminal | they connect to the switch directly |

[Issue #2](https://github.com/bitsandbricks-ch/floorbit/issues/2) tracks the rest.

## Enrolling an agent

**Settings > Local agents** (`/settings/agents`): give the agent a name, such as the event or the
site, and press **Enrol**. An admin enrols the agent and gets its **key**, `fba_<id>_<secret>`. The key is shown once; Floorbit
keeps only a hash of it (in `data.json`, under `agents`). Give the key to the agent as `FLOORBIT_AGENT_KEY`, never in a file anyone can read. The page shows
the `docker run` line to start the agent with it.

The page lists every agent: **Connected** or not, when it was last seen, its version, and who
enrolled it when. It updates every 10 seconds. For the last hour it also shows how many calls the
agent answered, how long it took (the median, from handing a call out to getting its answer), how
many failed, and the last error with its method. A slow LibreNMS or one that refuses the agent's
token shows up there first. These numbers are kept in memory, so a restart starts them over. An agent that speaks an older
agent protocol than the hosted Floorbit gets an **Update** badge: pull the new image and start it
again (below). An agent that hasn't asked anything yet is never flagged. An agent that sent syslog or a
traffic summary in the last ten minutes gets a **Syslog** or **NetFlow** badge, so it's clear which
agent forwards what.

Revoking the agent stops it at its next request, and an open WebSocket link is closed within a few
seconds: it has to be enrolled again with a new key. Up to
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

The agent has its own repository, [bitsandbricks-ch/floorbit-agent](https://github.com/bitsandbricks-ch/floorbit-agent),
with its own image (`ghcr.io/bitsandbricks-ch/floorbit-agent`) and releases. It carries Floorbit's
plugins but no web pages. Run it on the event network, where it can reach LibreNMS and NetBox. It
needs no Redis, no port and no domain. Any agent release works with any Floorbit that speaks its
protocol (see [The protocol](#the-protocol)).

**With Docker Compose** (this repository and the agent's both have a file for it):

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
  ghcr.io/bitsandbricks-ch/floorbit-agent
```

**Check the setup first.** `check` tries each part once (the hosted Floorbit and the key, the
monitoring plugin, the inventory and health plugins, and, when their ports are set, whether the
hosted Floorbit takes syslog and flows), says which works and which doesn't, and exits with 0 when
everything works, 1 when something doesn't:

```sh
docker compose -f docker-compose.agent.yml run --rm agent python -m floorbit_agent check
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
| `FLOORBIT_AGENT_PLUGINS` | more plugins to turn on there, comma-separated, such as `http-check`. Only LibreNMS and NetBox are on by default. A plugin's settings come from `FLOORBIT_PLUGIN_<ID>_<KEY>`, for example `FLOORBIT_PLUGIN_HTTP_CHECK_TARGETS=Cache=http://cache.lan.example/health` |
| `FLOORBIT_AGENT_SYSLOG_PORT` | a UDP port to take syslog on, such as `5514`, sent on to the hosted Logs page. Unset: the agent doesn't listen. `FLOORBIT_AGENT_SYSLOG_BIND` picks the address (all of them by default) |
| `FLOORBIT_AGENT_FLOWS_PORT` | a UDP port to collect NetFlow and IPFIX on, such as `2055`, for the hosted Traffic page. Unset: no collector. `FLOORBIT_AGENT_FLOWS_BIND` picks the address; the `FLOWS_*` settings of [Traffic](flows.md) apply on the agent |
| `FLOORBIT_AGENT_HEARTBEAT` | where the heartbeat file for `health` goes (next to its settings file by default) |
| `FLOORBIT_AGENT_INSECURE` | `1` allows an `http://` URL, for a test on a trusted network only: the key and the event data go over it |
| `FLOORBIT_DATA_FILE` | the agent's own settings file (in the image `/app/state/data.json`, elsewhere `agent-data.json` in its working directory). It keeps no floor plan |

The agent only makes outgoing requests; nothing listens on it unless `FLOORBIT_AGENT_SYSLOG_PORT` or `FLOORBIT_AGENT_FLOWS_PORT` is set. It runs up to 4 calls side by side,
so one slow port lookup doesn't hold up the floor plan. When the hosted Floorbit can't be reached,
it tries again after 1 second, then 2, 4 and so on, up to a minute between tries, and logs each
try. When the key is refused (wrong or revoked), it stops with exit code 1: enrol it again and
start it with the new key. That's why the Compose file restarts it only on failure, at most 3
times, instead of `unless-stopped`. Stopping it (`docker stop`, Ctrl+C) first sends the syslog
lines still waiting, so an update doesn't lose them.

**Health.** `python -m floorbit_agent health` exits with 0 when the hosted Floorbit answered the
agent in the last two minutes, 1 otherwise. It reads a heartbeat file the agent writes after each
poll that gets through, so it needs no network and no settings. The Compose file uses it as the
container's health check, so `docker ps` shows the agent as *unhealthy* while the uplink is down.

To update the agent, pull the new image and start it again (`docker compose -f
docker-compose.agent.yml pull && docker compose -f docker-compose.agent.yml up -d`). The
**Local agents** page shows each agent's version, and **Update** next to one that speaks an older
agent protocol than this Floorbit.

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

## Health checks through the agent

The [health wall](health.md) checks services such as the LAN cache or a game server's web panel,
which are usually only reachable inside the hall. Turn the health plugins on on the agent
(`FLOORBIT_AGENT_PLUGINS=http-check` and `FLOORBIT_PLUGIN_HTTP_CHECK_TARGETS=…`) and the hosted
health wall shows their checks, made from the event network, as "HTTP check (local agent)". A
plugin the agent checks with isn't also asked on the hosted side. While the agent is away, the
wall shows one grey "Local agent" tile instead of the checks.

## DNS analytics through the agent

Turn the DNS plugin on on the agent (`FLOORBIT_AGENT_PLUGINS=pihole` with
`FLOORBIT_PLUGIN_PIHOLE_URL` and so on, or `adguard-home`) and the hosted [DNS page](dns.md) counts
the hall's lookups as with a local resolver. The agent makes them safe to send first: each client's
address becomes a keyed hash (the key lives only in the agent's memory), and names are cut to the
site, with local names (a machine's name says whose it is) left out. So neither addresses nor
machine names leave the event network; the hosted side applies the same 5-client rule as always.

## Wi-Fi through the agent

With the UniFi plugin on on the agent (`FLOORBIT_AGENT_PLUGINS=unifi` and its
`FLOORBIT_PLUGIN_UNIFI_…` settings), the hosted [Wi-Fi page](wifi.md) shows the access points, their
channels and client counts, marked "UniFi (local agent)". The agent cleans the controller's answer
first, so only counts leave the event network, never client names or MACs. The Wi-Fi link in the
menu only shows when the hosted Floorbit has a Wi-Fi plugin of its own; open the page at `/wifi`.

## Syslog through the agent

Syslog is UDP, unencrypted and unauthenticated: the switches shouldn't send it across the internet
to a hosted Floorbit. Let the agent take it instead. Set `FLOORBIT_AGENT_SYSLOG_PORT=5514`, publish
the port (in `docker-compose.agent.yml`, uncomment the `ports` lines, which map the host's
udp/514 to it) and point the switches, firewalls and DHCP servers at the agent's machine, as
[Syslog](syslog.md) describes for a Floorbit of your own.

The agent sends the lines on over its HTTPS connection every two seconds, each with the address
it came from and when it arrived. The hosted Floorbit treats them as if they had come straight to it:

- The **Syslog** feature has to be on there (it is by default). `SYSLOG_ENABLED` doesn't matter: it
  only opens the hosted server's own port.
- The **allow-list** applies to the original senders: the switches' management addresses from the
  inventory, and `SYSLOG_ALLOW` set on the hosted Floorbit to the event's other senders (firewall,
  DHCP servers). Lines from anyone else are dropped and counted, as usual.
- The rate cap, retention and Loki forwarding are the hosted side's.

While the hosted Floorbit can't be reached, the agent keeps up to 20,000 lines and sends them when
it's back, with the time it got them. Past that it drops the newest and counts them; the Logs page
shows the count next to "Through the local agent …".

## Traffic (NetFlow) through the agent

Flows are too many, and too revealing, to send across the internet one by one. So the agent runs
the [flow collector](flows.md) itself: set `FLOORBIT_AGENT_FLOWS_PORT=2055`, publish the port
(the `ports` lines in `docker-compose.agent.yml`) and point the routers and firewalls' NetFlow or
IPFIX export at the agent's machine.

- Every 10 seconds the agent sends the hosted Floorbit **only the summary** the Traffic page shows:
  hall, area and service totals, services only once enough seats used them (`FLOWS_MIN_SEATS`), and
  per seat the volume and category mix. The page says "collected by the local agent …".
- The **flow records**, with addresses and ports, stay on the agent, in its state volume, for
  `FLOWS_RETENTION_DAYS` (7). `FLOWS_KEEP_RAW=false` on the agent keeps none.
- To count per seat the agent needs the seats' addresses. It asks the hosted Floorbit for them
  every minute (`GET /api/agent/v1/seats`), so they reach the event network's own machine, and
  nowhere else.
- The **Traffic** feature has to be on on the hosted Floorbit. Own classification rules
  (`FLOWS_RULES`) are read on the agent.
- With several agents, let one of them collect flows: each summary replaces the last.

## What the agent says about itself

Every half minute the agent sends a short report: how long it has been up, how often its link
dropped, the syslog lines it received, still holds and dropped, the NetFlow packets it read and the
calls it answered "busy" because too many of one kind were waiting. The Local agents page shows it
under each agent, with dropped lines and busy calls in colour. Only these numbers are kept, only
in memory, and a report older than three minutes isn't shown. The agent's own `/metrics` has
the full detail for Prometheus.

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

The agent sends its key in the `Floorbit-Agent-Key` header, its version in
`Floorbit-Agent-Version` and the protocol it speaks in `Floorbit-Agent-Protocol` (`1` or `2`; no
header counts as `1`). It needs no account and no session.

The protocol has its own number because the agent and Floorbit are released apart. A change the other
side can't follow gets a new number. A Floorbit that doesn't speak the agent's protocol answers every
agent request with **426** and says which one it speaks. The agent then stops with exit code 1, like
for a revoked key, because retrying won't help: update the agent or Floorbit. `hello` says which
protocol the hosted Floorbit speaks (`"protocol"`) and which ones it understands (`"protocols"`).

### The WebSocket link (protocol 2)

When `hello` lists `2` in `protocols`, the agent opens a WebSocket to `"link"`
(`wss://…/api/agent/v2/link`, TLS like everything else) with the same headers. Calls reach it the
moment they are made, over one connection that stays open, instead of one long poll after another.
The messages are JSON:

| From | Message |
| --- | --- |
| Floorbit | `{"type": "hello", "name", "protocol"}` once, when the link opens |
| Floorbit | `{"type": "calls", "calls": [{"id", "method", "args"}]}`: the same calls as the long poll |
| agent | `{"type": "answers", "answers": [{"id", "ok", "result", "error"}]}`: the same answers |
| agent | `{"type": "report", "report": {…}}` every half minute: its own numbers, shown on the Local agents page (below) |
| both | `{"type": "ping"}` at least every 20 seconds, plus WebSocket pings, so proxies keep it open |

A wrong or revoked key gets a plain 401 before the upgrade. An agent silent for a minute is closed
and reconnects. Syslog and flow summaries stay on their HTTPS posts below.

If the link can't be opened, say a proxy on the way doesn't pass WebSockets, the agent falls back
to the long poll by itself and tries the link again later. The reverse proxy in front of a hosted
Floorbit needs to pass the upgrade for `/api/agent/v2/link` (nginx: `proxy_http_version 1.1` and the
`Upgrade` and `Connection` headers; Caddy and Traefik do it by themselves).

| Request | What |
| --- | --- |
| `GET /api/agent/v1/hello` | checks the key: `{"name", "server_version", "encodings", "protocol", "protocols", "link"}`, or 401 |
| `GET /api/agent/v2/link` | the WebSocket link (protocol 2, above), or 401 |
| `GET /api/agent/v1/calls?wait=25` | the calls waiting for the agent, `{"calls": [{"id", "method", "args"}]}`; waits up to `wait` seconds (at most 25) for the first one |
| `POST /api/agent/v1/answers` | `{"answers": [{"id", "ok", "result", "error"}]}`; `{"taken": n}` says how many were still awaited |
| `POST /api/agent/v1/report` | `{"report": {"up_seconds", "reconnects", "link_drops", "calls_busy", "answers_failed", "syslog_received", "syslog_sent", "syslog_dropped", "syslog_backlog", "flows_packets"}}`: the report above, from an agent on the long poll |
| `POST /api/agent/v1/syslog` | `{"lines": [{"raw", "from", "at"}], "dropped"}`: up to 2,000 syslog lines; `{"taken", "received"}`, or 409 while Syslog is off |
| `GET /api/agent/v1/seats` | `{"seat_of", "area_of"}`: the seat addresses for the flow collector, or 409 while Traffic is off |
| `POST /api/agent/v1/flows` | `{"snapshot"}`: the flow collector's summary, or 409 while Traffic is off |

When `hello` lists `gzip` in `encodings`, the agent sends POST bodies over 2 KB gzipped
(`Content-Encoding: gzip`), which saves most of the uplink on syslog batches and inventories. A body
that doesn't unpack, or unpacks to more than 32 MB, counts as empty.

The methods are those of the monitoring source (see [architecture.md](architecture.md#inventory-and-data-sources)):
`configured`, `devices`, `device_details`, `resolve_ip`, `port_stats`, `device_ports` and `arp`, plus
`inventory_feeds`, which answers `[{"plugin", "name", "items"}]` (or `"error"` instead of `"items"`) for each
inventory plugin that's on, and `cable_feeds`, the same for each plugin that knows cables. Nothing else can be asked. The agent answers with what its own monitoring plugin returns.

For admins (**Manage settings**):

| Request | What |
| --- | --- |
| `GET /api/agents` | the enrolled agents (name, when made and by whom, last seen, version, connected, `protocol` (the one it spoke last), `outdated` (that protocol is older than this Floorbit's), and `stats`: the last hour's `calls`, `failed`, `median_ms` and `last_error`, and `relays`: what it sent in the last ten minutes, `syslog` and `flows` with `at` and `count`), `server_version` and `protocol` |
| `POST /api/agents` | `{"name"}`: enrol one. The answer holds `key`, this once |
| `PATCH /api/agents/<id>` | `{"halls": [ids]}`: the halls it answers for, empty for every hall |
| `DELETE /api/agents/<id>` | revoke it |

API tokens can't reach `/api/agents`, so a leaked token can't enrol an agent.
