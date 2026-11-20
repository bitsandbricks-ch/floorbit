# Local agent

**The local agent is the only way Floorbit reaches the event network**, whether Floorbit is hosted on
the internet or runs on a server in the hall. One path for both: what works self-hosted works hosted,
and both are tested the same way. A self-hosted install runs the two side by side (the compose file
starts both, [install.md](install.md)).

The Floorbit server itself never asks LibreNMS, NetBox, a switch, a resolver or a smart PDU, and never
listens for syslog: those plugins run on the agent with the settings made here, and the server
refuses to call their network methods itself. Without a connected agent, pages show their last
known state, greyed out with "stale since", and say that no agent is connected; nothing breaks.
There is no switch to turn this off: development and tests run an agent too. The demo data
(`FLOORBIT_DEMO`) needs no agent.

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
| The Wi-Fi widget (UniFi as a Wi-Fi source, turned on there) | wifi |
| Syslog on the Logs page, when the agent listens for it (the **Syslog from the hall** plugin) | syslog |
| The Traffic page (NetFlow and IPFIX), when the agent collects flows (the **Traffic from the hall** plugin) | traffic |
| Port actions (SSH ports), switch commands, config backups and the switch terminal | switch SSH |
| Attendee check-in, the seat help page and its speed test, with each PC's own address | front door |

Pages that only use Floorbit's own data work anyway: seats, incidents, schedule, electrics
readings typed in, tournaments, and so on.

[Issue #2](https://github.com/bitsandbricks-ch/floorbit/issues/2) tracks the rest.

## Where the hosted server's own requests may go

Admins set many URLs: NetBox, LibreNMS, sign-in providers (OIDC), HTTP seat sources, webhooks, Loki
and plugin base URLs. Every request the server makes is checked against the address it actually
connects to, after DNS, so a name that is changed to point somewhere else later (DNS rebinding) is
still caught:

- **Always refused**, also on a self-hosted Floorbit: link-local addresses (`169.254.0.0/16`,
  `fe80::/10`, where clouds keep their metadata service), `0.0.0.0` and multicast, also through IPv6
  that carries one of those inside (`::ffff:`, NAT64 `64:ff9b::`, 6to4 `2002::`).
- **`OUTBOUND_BLOCK_NETS`** refuses more. On a hosted Floorbit, set it to loopback and the hosting
  network's own ranges, for example `127.0.0.0/8,::1/128,10.42.0.0/16`, so that no tenant admin can
  point a URL at the hosting side. Leave it empty on a self-hosted Floorbit: NetBox and LibreNMS sit on
  the LAN there.

A refused request fails like an unreachable server, with "Refused: ..." in the error. Through an HTTP
proxy (`HTTPS_PROXY`) the server connects to the proxy, so only the proxy's address is checked: let the
proxy refuse the hosting network too. The server's own probes, game server queries and RCON follow
`PROBE_NETS` ([services](services.md#what-the-server-itself-may-reach)).

## The agent next to a self-hosted Floorbit

`docker-compose.yml` and the Kubernetes manifest start the agent next to Floorbit, and it enrols
itself: with `FLOORBIT_LOCAL_AGENT_KEY_FILE` set, Floorbit writes a key into that file at start
(mode 600, in a volume only the two containers share) and keeps the agent as **Local agent** (id
`10ca1000`). The agent reads it from `FLOORBIT_AGENT_KEY_FILE` (it waits up to two minutes for the
file) and connects to `http://floorbit:5000` inside the Compose network, or `http://localhost:5000`
in the pod. The file is the truth: a key written there by hand is taken over at the next start.
**Renew key** on Settings writes the new key to the file as well; the agent takes it at its next
start, and the old key keeps working until then (at most 24 hours). Revoking it removes it only
until Floorbit's next start: to run without it, remove the `agent` service.

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

**Rename** changes the name it is shown and logged under. **New key** makes another key, shown once
like the first: the old key keeps working until the agent first uses the new one, 24 hours at most,
so the hall can swap it without the agent going dark. **Plugins it leaves off** lists plugins that
are on here but that this agent doesn't start, because another agent runs them (the LAN cache
plugin on the agent next to the cache, say). Each agent also shows the version of every plugin it
runs, an update that waits and why, and its last rollouts ([agent-plugins.md](agent-plugins.md),
"Updates"). All of these are written to the [audit log](audit.md).

**This Floorbit** at the top says how the hosted side itself stands: one instance, or several
sharing Redis ([kubernetes.md](kubernetes.md)) with the one that leads; and whether the database and
Redis answer.

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

### Two agents in one hall (failover)

Agents that answer for the same halls back each other up. For the event network to reach them at
one address that moves, turn on VRRP in the agents (floorbit-agent's `docs/vrrp.md`): they share
virtual IPs, and the agent holding the first one is the hall's **primary**.

- **Active/passive:** every VIP on one agent (the same `FLOORBIT_AGENT_VRRP_PREFER` on both). The
  standby only takes over.
- **Active/active:** the VIPs spread over the agents (`PREFER` 1 on one, 2 on the other). Both take
  syslog, NetFlow and traps sent to their address, and both answer this Floorbit's calls.

Either way only the primary polls devices and logs in to them (agent plugins ask `ctx.primary()`,
and a standby's `may_login` is always no), so no device is polled twice and no login is tried twice.
Syslog that reached both agents is kept once (each line has the same id on every agent), and a
standby's NetFlow summary doesn't replace the primary's on the Traffic page. Point devices' syslog,
NetFlow and traps at the first VIP.

**Agents per hall** on the Local agents page shows each group: who is primary or standby, which
addresses each holds, active/active or active/passive, and what needs a look: **Backup missing**
(a standby is offline), **No VRRP** (several agents without it, so each polls), **Two primaries**
(they can't hear each other: check the VLAN or set `FLOORBIT_AGENT_VRRP_PEERS`), **No primary**, or
**One agent** (no failover).

**Two primaries** (split brain) is settled here as well: when a switch or a cable between the agents
drops their VRRP, each takes every address and calls itself primary. This Floorbit hears both, so
it tells all but the one with the smallest id to stand by (with the plugin config they pull, within
seconds). They keep their addresses and listeners but leave polling and logins to that one, so no
account is locked by two agents trying it. If this Floorbit can't reach them either, VRRP alone
decides until it can. Older agents ignore the hint and keep polling (floorbit-agent's
`docs/vrrp.md`, "Split brain").

## Running the agent

The agent has its own repository, [bitsandbricks-ch/floorbit-agent](https://github.com/bitsandbricks-ch/floorbit-agent),
with its own image (`ghcr.io/bitsandbricks-ch/floorbit-agent`) and releases. It carries Floorbit's
plugins but no web pages. Run it on the event network, where it can reach LibreNMS and NetBox. It
needs no Redis, no port and no domain. Any agent release works with any Floorbit that speaks its
protocol (see [The protocol](#the-protocol)).

**With Docker Compose** (this repository and the agent's both have a file for it):

```sh
cp agent.env.example agent.env     # fill in FLOORBIT_URL and FLOORBIT_AGENT_KEY
chmod 600 agent.env
docker compose -f docker-compose.agent.yml up -d
docker compose -f docker-compose.agent.yml logs -f    # "[agent] connected to … as …"
```

**With `docker run`**, as the **Local agents** page shows it:

```sh
docker run -d --restart on-failure:3 --name floorbit-agent \
  -e FLOORBIT_URL=https://floor.example.com \
  -e FLOORBIT_AGENT_KEY=fba_… \
  -v floorbit-agent:/app/state \
  -p 443:8443 -p 80:8080 -p 162:1162/udp -p 57000:57000 \
  ghcr.io/bitsandbricks-ch/floorbit-agent:<version>
```

The page fills in the image tag: the agent commit this Floorbit is built and tested with
(`AGENT_REF`), so the two don't drift apart. The volume keeps the agent's state (its certificate
and settings) over an update. The ports are those of what is on by default: attendees on 443 and
80, SNMP traps and Cisco model-driven telemetry. For a Floorbit on plain `http://` (a test), the line
also sets `FLOORBIT_AGENT_INSECURE=1`, and the page warns that the key then travels unencrypted.

**Check the setup first.** `check` tries each part once (the hosted Floorbit and the key, the
monitoring plugin, the inventory and health plugins, and the plugins that run on the agent), says which works and which doesn't, and exits with 0 when
everything works, 1 when something doesn't:

```sh
docker compose -f docker-compose.agent.yml run --rm agent python -m floorbit_agent check
```

```text
OK   https://floor.example.com accepts the key: this is "Spring LAN, hall 2" (Floorbit 0.1.0)
OK   the monitoring plugin answers: 24 devices
FAIL NetBox: Set the NetBox URL and API token under Settings > NetBox first.
Fix what failed, then run the check again.
```

### Settings come from Floorbit

Everything the agent does for the event is a plugin, set up in Floorbit under **Settings >
Plugins**: LibreNMS and NetBox, health checks, DNS, Wi-Fi, and the parts that listen in the hall
(**Syslog from the hall**, **Traffic from the hall**, **Check-in note on phones** and **Front door
for attendees**). Every agent takes them from there within a minute. The agent's own environment no
longer sets plugins: `LIBRENMS_URL`, `NETBOX_URL`, `FLOORBIT_PLUGIN_<ID>_<KEY>`,
`FLOORBIT_AGENT_PLUGINS` and the old `FLOORBIT_AGENT_SYSLOG_PORT`, `_FLOWS_PORT`, `_CAPTIVE` and
`_FRONT_DOOR` are not read.

**Updating an agent that still has them.** So the event keeps running, the agent sends what its
environment set for plugins once, over its link, and Floorbit takes it over for each plugin that
isn't on and has no saved settings there yet, tokens included (sealed like any other plugin token).
A plugin already set up in Floorbit keeps its settings. The audit log has an entry per plugin taken
over ("Took over plugin settings from an agent"), and the agent's log says which variables you can now
remove. Only plugins that work on an agent are taken over this way.

**Self-hosted with the agent next to Floorbit** (the compose file, the Kubernetes pod): the first
time Floorbit starts with its local agent, it turns on syslog on port 5514, flows on 2055 and the
front door on `0.0.0.0:8443`, the ports the compose file and the pod publish. A plugin you set up or
turned off yourself is left alone.

### The agent's own settings

Each agent's own settings are set on its page in Floorbit (**Agents >** the agent **> Settings**), and
the agent takes them with its plugins: the address laptops in the hall use, the metrics listener and
its token, how much it buffers while Floorbit is away, the Telegraf port, the log level and summary
line, and the VRRP virtual IPs. Plugin settings that differ on one agent (another flow port, another
syslog bind) are set there too; **Settings > Plugins** stays the default for every agent.

**The agent's environment wins.** When the agent's own environment sets one of them
(`FLOORBIT_AGENT_LAN_URL`, `FLOORBIT_AGENT_METRICS`, `_METRICS_TOKEN`, `_BUFFER_MAX_MB`,
`_BUFFER_MAX_HOURS`, `FLOORBIT_TELEMETRY_PORT`, `FLOORBIT_AGENT_LOG_LEVEL` (or `LOG_LEVEL`),
`_LOG_SUMMARY`, `FLOORBIT_AGENT_VRRP_*`), that value is used and the field on the page is locked.
The agent reports where each value came from (*agent env*, *Floorbit* or *default*), and which ones
wait for its next start: the address and the log level apply at once, the rest when it starts again.
It keeps what Floorbit sent in `agent-settings.json` in its state folder (readable only by it), so it
starts with them even while Floorbit is out of reach. A token set in Floorbit is sealed there and
only sent to that agent; the page shows it as set, never its value.

What stays in the agent's environment:

| Setting | What |
| --- | --- |
| `FLOORBIT_URL` | the hosted Floorbit, `https://…` |
| `FLOORBIT_AGENT_KEY` | the key from **Agents**, to enrol it; a rolled key replaces it (below) |
| `FLOORBIT_AGENT_ALLOW_ACTIONS`, `FLOORBIT_AGENT_PLUGIN_UPDATES` | what the people at the hall allow (actions, plugin updates) |
| `FLOORBIT_AGENT_SWITCH_NETS`, `_GAME_NETS`, `_PROBE_NETS` | which networks it may reach |
| `FLOORBIT_AGENT_TLS_CERT`, `FLOORBIT_AGENT_TLS_KEY` | a certificate of your own, instead of the one Floorbit signs (below) |
| `FLOORBIT_AGENT_HEARTBEAT` | where the heartbeat file for `health` goes (next to its settings file by default) |
| `FLOORBIT_AGENT_INSECURE` | `1` allows an `http://` URL, for a test on a trusted network only: the key and the event data go over it |
| `FLOORBIT_DATA_FILE` | the agent's own settings file (in the image `/app/state/data.json`, elsewhere `agent-data.json` in its working directory). It keeps no floor plan |

The limits (actions, plugin updates, networks) are only ever set in the hall, and the agent's page
shows them read-only as the agent reports them: a stolen Floorbit login must not widen what an agent
can reach or do.

### Rolling an agent's key

**Roll key** on the agent's page (or for every agent at once, `POST /api/agents/roll`) makes a new
key; the agent fetches it on its next pull and keeps it in `agent-key` in its state folder, readable
only by it. Nothing in its environment has to change: a stored key wins over `FLOORBIT_AGENT_KEY`,
which only enrols it. The old key keeps working until the agent uses the new one, for 24 hours at
most, so an answer lost on the way doesn't lock the agent out. When Floorbit refuses the stored key
(the agent was revoked and enrolled again), the agent moves it aside and starts with the key in its
environment. **New key** still makes a key to copy by hand, for an agent that is offline.

### Certificates for the agent

The front door and the telemetry listener answer HTTPS. Floorbit runs its own certificate authority
for its agents: each agent makes its own key (it never leaves the agent) and sends a signing request;
Floorbit signs it for the names listed under **Names on the certificate** on the agent's page, and
only those, whatever the request asks for. A certificate lasts 397 days, the longest phones and
browsers accept, and the agent asks for a new one 30 days before the end, when the names change, or
when someone presses **New certificate**. It keeps it in `tls/` in its state folder.

Crew devices install the CA once (**Download CA** on the agent's page, `GET /api/agents/ca.pem`)
and then trust every agent of this Floorbit. The CA's key is sealed with the vault. A certificate set
in the agent's environment (`FLOORBIT_AGENT_TLS_CERT`, `_TLS_KEY`) wins, for a hall that uses its own.

The agent only makes outgoing requests; nothing listens on it unless a plugin that listens is on (syslog, flows, the check-in note, the front door). It runs up to 4 calls side by side,
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

## Ports

The agent connects out and needs no open port for its own work. Each port below belongs to a plugin
that listens in the hall; publish it (the `ports:` of the agent in `docker-compose.agent.yml`, or the
agent repository's `compose.yml`) when you use that plugin, and point the devices at the agent
machine's address. Inside the container the ports are above 1024, so the agent runs as a normal user;
the left side of a mapping is what the devices send to.

| Port in the container | Published as | Plugin | What sends to it | Published by default |
| --- | --- | --- | --- | --- |
| 9520/tcp | `127.0.0.1:9520` | the agent itself | `/healthz`, `/metrics` for Prometheus | yes, this machine only |
| 1162/udp | `162/udp` | Telemetry | SNMP traps from switches and firewalls | yes |
| 57000/tcp | `57000` | Telemetry | Cisco model-driven telemetry, dial-out (gRPC) | yes |
| 8186/tcp | `8186` | Telemetry | a firewall's own Telegraf (OPNsense, pfSense) | no |
| 5514/udp | `514/udp` | Syslog from the hall | syslog from switches, firewalls, DHCP | no |
| 2055/udp | `2055/udp` | Traffic from the hall | NetFlow v5/v9 and IPFIX exports | no |
| 8908/tcp | through the reverse proxy | Check-in note on phones | phones and laptops (RFC 8908), via DHCP option 114 | no |
| 8443/tcp | `80` or `443` | Front door for attendees | attendees' browsers | no |

Another trap receiver on the same machine (LibreNMS's snmptrapd) already holds 162: set
`TRAP_PUBLISH_PORT` to another port and point the devices there, or send traps to one of the two.

**What to check, port by port.** Each plugin's numbers are on **Settings > Local agents**, on the
agent's page, and in `/metrics` as `floorbit_agent_plugin_<name>{plugin="<id>"}`:

| Port | Check | Works when |
| --- | --- | --- |
| 9520 | `curl -s http://127.0.0.1:9520/healthz` on the agent machine | it answers 200 with `"ok": true` |
| 162/udp, 57000 | `docker compose logs agent \| grep telemetry` after a port goes down and up on a switch | the port changes on the floor plan within seconds; Telegraf's own complaints show in the agent's log with the device's name |
| 8186 | from the firewall: `curl -s -o /dev/null -w '%{http_code}' http://<agent>:8186/ping` | `204` |
| 514/udp | `logger -n <agent> -P 514 -d "floorbit test"` from any machine | the line is on the Logs page; `received` grows for `syslog-relay` |
| 2055/udp | a router's flow export pointed at it | `packets` grows for `netflow-relay`; the Traffic page fills after a minute |
| 8908 | `curl -s http://<agent>:8908/.well-known/captive-portal` | a JSON answer with `captive` in it |
| 8443 | open `http://<agent>/` from a seat | the check-in page |

## Telegraf

Device telemetry (SNMP polling and traps, gNMI, Cisco MDT; [telemetry.md](telemetry.md)) is
collected by [Telegraf](https://www.influxdata.com/time-series-platform/telegraf/). The agent image
carries it, and the **Telemetry** plugin runs it inside the agent: there is no second container to
start and no Compose profile. The plugin writes Telegraf's config from the devices set up in Floorbit,
starts Telegraf, tells it to reload when the devices change, starts it again when it stops, and
reads every line it prints.

That is how Floorbit knows why a device sends nothing. Telegraf's errors become a problem per device
and kind of collection (nothing listening, no answer, login refused, no route, TLS), shown in words
on the agent's page and next to each device under **Monitoring > Telemetry**, with what to check
([telemetry.md, "When a device sends nothing"](telemetry.md#when-a-device-sends-nothing)). The agent's
log gets a line when Telegraf starts, stops or reloads, when a device is first heard or comes back,
each new problem, each **Test now** and its result, every minute what each device gave (and which gave
nothing), and every five minutes how many points came in from how many devices:

```text
[telemetry] Telegraf started (pid 41)
[telemetry] sw-a-01 heard: 52 ports via snmp, 840 MACs
[telemetry] core-01 (snmp): nothing listens for SNMP on 192.0.2.1:161: is it turned on there, and the port right?
[telemetry] polls, last minute: 3640 points from 12 of 13 devices: sw-a-01 412, sw-a-02 398, ...
[telemetry] nothing in the last minute from 1: core-01 (nothing listens for SNMP ...)
[telemetry] Test now on sw-a-01 (snmp, traps)
[telemetry] Test now on sw-a-01: 412 points in 840 ms
[telemetry] last 5 min: 18200 points from 12 devices, 12 of 13 heard
```

On an agent with `FLOORBIT_AGENT_LOG_LEVEL=debug`, Telegraf's own lines, each post it makes and each
API poll round are logged too. Each line in the agent's log also carries the time and the level (the
agent's README, "The log").

**Test now** (Monitoring > Telemetry, or a device's Telemetry tab) runs Telegraf once for that one device on the agent
and shows what came back (values, ports, the device's own name) or the exact error, in a few seconds.
**Raw data** shows the last lines the agent received from a device, as Telegraf sent them. Both are
asked of the agent when you open them; nothing extra is stored.

**Coming from a telegraf container.** Earlier agent releases needed a `telegraf` service next to the
agent (`docker compose --profile telemetry up -d`). Remove that service from your compose file and
run `docker compose up -d --remove-orphans`, so the old container goes too and frees ports 162 and
57000 for the agent. If it keeps running, the agent refuses what it polls (Telegraf in the agent does that now) and
the Telemetry plugin says so on the agent's page. To keep Telegraf in its own container anyway, set
`FLOORBIT_TELEGRAF=sidecar` on the agent: it then writes `/app/state/plugins/telemetry/telegraf.conf`
for that container and runs none itself.

## The inventory through the agent

Turn the event's inventory plugin on under Settings > Plugins (NetBox, with its URL and token);
the agent runs it too. An inventory sync on the hosted Floorbit (**Inventory > Sync**, or **Sync
switches** in the editor) then also asks the agent: it runs each inventory plugin that is on there
and sends back their devices. They are merged under the plugin's own id (`netbox`), the same as a
local install would, so a hall that moves from a local Floorbit to a hosted one keeps its devices,
their positions and the fields you edited by hand.

The inventory page lists the agent's plugins as, for example, "NetBox (local agent)", with their last
sync. A plugin that fails on the agent fails on its own; the others still sync. If the agent is away,
the sync says so and nothing changes. A sync waits up to 25 seconds for the agent.

A plugin the agent feeds is not asked on the hosted Floorbit itself, which can't reach it anyway.

## Switch logins through the agent

[Port actions](ports.md), [switch commands](commands.md), [config backups](configs.md) and the
[terminal](terminal.md) open their SSH connection on the agent, in the hall. The agent turns on the
same **SSH port actions** plugin with the hosted settings; nothing to set on the agent.

- **What stays on the hosted side:** who may do it, the cooldowns and failed-login pauses, the audit
  log, the stored logins and the pinned host keys. A stored login is opened for the one call and
  sent with it over the agent's link (TLS); the agent drops it when the connection is done and never
  writes it down. A typed login goes the same way.
- **Host keys** stay pinned on the hosted side and go along with each call, so two agents in one
  hall, or an agent that was replaced, check a switch against the same key. **Forget pinned host
  keys** works as before.
- **Which agent:** the one serving the switch's hall ([several agents](#several-agents)); with two
  in one hall, always the same one of them, so a terminal stays with the agent that opened it.
- **What the agent will reach:** only private addresses, or the networks in
  `FLOORBIT_AGENT_SWITCH_NETS` (comma separated) on the agent. A hosted Floorbit that was taken
  over can't send the agent to log in anywhere else.
- **Terminals** live on the agent (at most 10). The browser reads them through the hosted side as
  before; a terminal nobody reads for 90 seconds is closed on the agent. If the agent goes away,
  the terminal says the connection was lost.

## Attendees through the agent (front door)

A hosted Floorbit sees every attendee as the hall's one public NAT address, so check-in can't tell
which PC asks, the seat speed test measures the internet line, and all attendees share one
sign-in lockout. The agent's **front door** fixes that: it answers on the event network and passes
each request on to the hosted Floorbit, adding the address it saw and its own key.

Turn on the **Front door for attendees** plugin under Settings > Plugins:

| Setting | Example | What |
| --- | --- | --- |
| Address on the agent | `0.0.0.0:8443` | Where it answers (host:port). Empty: off. |
| Reverse proxy addresses | `10.0.0.5` | A reverse proxy in front of the agent: its last `X-Forwarded-For` hop is the client. |

For HTTPS, give the agent's machine a certificate (`FLOORBIT_AGENT_TLS_CERT` and
`FLOORBIT_AGENT_TLS_KEY` in its environment). Crew sign-in needs it (session cookies only go over
HTTPS); check-in works on plain HTTP.

Then point the check-in name (`CHECKIN_ADDRESS`, for example `checkin.lan`) at the agent in the
event DNS: typing it on a PC opens the check-in page, through the agent. Self-hosted, Floorbit turns the
front door on for its local agent, and the compose file and the Kubernetes manifest open it on port
80 (`CHECKIN_PUBLISH_PORT` in compose).

**Check-in takes the seat PC's address only from the front door**, hosted or self-hosted alike: a
request's own address or `X-Forwarded-For` never names it. A check-in from anywhere else keeps the
seat and nick without an address or port.

- **The hosted side only believes the agent.** `Floorbit-Client-IP` counts only on a request that
  also carries a valid agent key (`Floorbit-Front-Door`); a revoked key stops counting within 30
  seconds. The agent drops whatever a client sends under those names, and `X-Forwarded-For`.
- **The speed test measures the hall.** Its data (`/help/<seat>/speed/ping`, `down`, `up`) is
  answered by the agent itself, with the same per-client budget, so the result is the seat's path
  to the agent. The result goes to the hosted side as before.
- **Nothing else is reachable through it.** It only talks to the hosted Floorbit, and never passes
  on the agent's own API (`/api/agent/`).
- **When the hosted side is away,** attendees get a short page in English and German that tries
  again every 30 seconds, instead of an error. The Local agents page counts what went through and
  what failed.

## Cables through the agent

**Cables > Import from NetBox** works the same way: the agent sends the cables of each plugin there
that knows them (NetBox), and they replace the last import as usual. A plugin the agent answered for
isn't asked on the hosted Floorbit too. The cable page lists "Local agent" among its sources.

## Health checks through the agent

The [health wall](health.md) checks services such as the LAN cache or a game server's web panel,
which are usually only reachable inside the hall. Turn a health plugin on under Settings > Plugins
(**HTTP check** with its targets) and the agent runs it too: the hosted
health wall shows their checks, made from the event network, as "HTTP check (local agent)". A
plugin the agent checks with isn't also asked on the hosted side. While the agent is away, the
wall shows one grey "Local agent" tile instead of the checks.

## DNS analytics through the agent

Turn a DNS plugin on under Settings > Plugins (Pi-hole or AdGuard Home, with its address and
token) and the agent asks it from inside the hall: the hosted [DNS page](dns.md) counts
the hall's lookups as with a local resolver. The agent makes them safe to send first: each client's
address becomes a keyed hash (the key lives only in the agent's memory), and names are cut to the
site, with local names (a machine's name says whose it is) left out. So neither addresses nor
machine names leave the event network; the hosted side applies the same 5-client rule as always.

## Wi-Fi through the agent

With the UniFi plugin on under Settings > Plugins, the agent asks the controller and the hosted [Wi-Fi page](wifi.md) shows the access points, their
channels and client counts, marked "UniFi (local agent)". The agent cleans the controller's answer
first, so only counts leave the event network, never client names or MACs. The Wi-Fi widget
only has data when the hosted Floorbit has a Wi-Fi plugin of its own.

## Syslog through the agent

Syslog is UDP, unencrypted and unauthenticated: the switches shouldn't send it across the internet
to a hosted Floorbit. Let the agent take it instead: turn on the **Syslog from the hall** plugin
under Settings > Plugins and set its UDP port (such as `5514`); every agent picks it up within a
minute (docs/agent-plugins.md). Publish the port (in `docker-compose.agent.yml`, uncomment the
`ports` lines, which map the host's udp/514 to it) and point the switches, firewalls and DHCP
servers at the agent's machine, as [Syslog](syslog.md) describes for a Floorbit of your own.

Lines wait in the plugin's disk spool (256 MB and 24 hours) and its numbers show on Local agents.

The agent sends the lines on over its HTTPS connection every two seconds, each with the address
it came from and when it arrived. The hosted Floorbit treats them as if they had come straight to it:

- The **Syslog** feature has to be on there (it is by default). `SYSLOG_ENABLED` doesn't matter: it
  only opens the hosted server's own port.
- The **allow-list** applies to the original senders: the switches' management addresses from the
  inventory, and `SYSLOG_ALLOW` set on the hosted Floorbit to the event's other senders (firewall,
  DHCP servers). Lines from anyone else are dropped and counted, as usual.
- The rate cap, retention and Loki forwarding are the hosted side's.

While the hosted Floorbit can't be reached, the agent keeps the lines in the plugin's disk spool
and sends them when it's back, oldest first.
Lines it had to drop are counted; the Logs page shows the count next to "Through the local
agent …".

Lines that come late keep their own time, back to `SYSLOG_RETENTION_HOURS`, so the Logs page shows
them when they happened. They don't raise [log alerts](syslog.md) (that was hours ago), and they
have a rate cap of their own, so a backlog neither gets cut nor crowds out the live lines.

Each line carries an ID made of its sender and text, the same on every agent that heard it. A second
copy within ten seconds of the first (two agents, or a batch sent again after a crash) is dropped
and counted as `duplicates` in the syslog status.

The agent's clock doesn't need to be right. Every request says the agent's time
(`Floorbit-Agent-Clock`), and Floorbit adds the difference to its own clock to the times the agent
sends, once it is more than 5 seconds. A box without NTP or a battery clock would otherwise make
every line look late, so no log alert fires, or past retention, so every line is dropped. From one
minute off, the Floorbit log says so once per agent. Older agents don't send the header, and their
times are taken as they are.

## Traffic (NetFlow) through the agent

Flows are too many, and too revealing, to send across the internet one by one. So the agent runs
the [flow collector](flows.md) itself: turn on the **Traffic from the hall** plugin under
Settings > Plugins and set its UDP port (such as `2055`), publish the port (the `ports` lines in
`docker-compose.agent.yml`) and point the routers and firewalls' NetFlow or IPFIX export at the
agent's machine. Only the newest summary waits while the hosted side is away.

- Every 10 seconds the agent sends the hosted Floorbit **only the summary** the Traffic page shows:
  hall, area and service totals, services only once enough seats used them (`FLOWS_MIN_SEATS`), and
  per seat the volume and category mix. The page says "collected by the local agent …".
- The **flow records**, with addresses and ports, stay on the agent, in its state volume, for
  `FLOWS_RETENTION_DAYS` (7) and at most `FLOWS_RAW_MAX_MB` (10 GB, the oldest hours go first).
  `FLOWS_KEEP_RAW=false` on the agent keeps none.
- To count per seat the agent needs the seats' addresses. It asks the hosted Floorbit for them
  every minute (`GET /api/agent/v1/seats`), so they reach the event network's own machine, and
  nowhere else.
- The **Traffic** feature has to be on on the hosted Floorbit. Own classification rules
  (`FLOWS_RULES`) are read on the agent.
- With several agents, let one of them collect flows: each summary replaces the last.

## What the agent says about itself

Every half minute the agent sends a short report: how long it has been up, how often its link
dropped, the syslog lines it received, still holds and dropped, the NetFlow packets it read, how often its captive portal showed
the check-in note or said it wasn't needed, and the calls it answered "busy" because too many of one kind were waiting. The Local agents page shows it
under each agent, with dropped lines and busy calls in colour. The latest report is kept in
memory, and one older than three minutes isn't shown. The agent's own `/metrics` has the full
detail for Prometheus.

A few of the numbers are also kept over time, for the **Graphs** tab on the agent's page: the
telemetry points and the sends to Floorbit per minute, the series, the devices heard and failing,
Telegraf restarts, reconnects and syslog lines per minute, and the median time the agent took to
answer. They are stored with the telemetry series (Floorbit's database, a point a minute for six
hours and every 15 minutes for `FLOORBIT_TELEMETRY_DAYS`; or VictoriaMetrics as `fb_agent_<name>`
with an `agent` label when it is set up) and age out with them. A gap in a graph is a time the
agent didn't report.

## When the agent is away

An agent counts as **connected** while it asked for work in the last 60 seconds, and over the
WebSocket link until the link closes: a stopped or killed agent is gone at once, not a minute later.
An agent that freezes or loses its line sends no close; when it sits on a call for 3 seconds without
a word, Floorbit pings it, and with no answer within 5 more seconds it closes the link and counts the
agent as gone. The calls it held fail with "went away before it answered; it may have run", so a
port action is looked at before it is tried again. Over the HTTPS long poll, which has no link to
close, a live agent is always asking for work: a call nobody took for 5 seconds while the agent
hasn't asked in 10 counts it as gone, and the calls after that fail at once until it asks again. A page that needs LibreNMS waits up to 8 seconds
for the agent's answer. If the agent is not connected or doesn't answer in time, Floorbit answers from the last good data it has, marked as stale with its age, as
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
| `POST /api/agent/v1/report` | `{"report": {"up_seconds", "reconnects", "link_drops", "calls_busy", "answers_failed", "syslog_received", "syslog_sent", "syslog_dropped", "syslog_backlog", "flows_packets", "captive_shown", "captive_done", "plugins"}}`: the report above, from an agent on the long poll |
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
