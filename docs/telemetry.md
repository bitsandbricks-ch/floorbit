# Device telemetry

Floorbit can hear from the hall's switches, routers and firewalls directly, without LibreNMS:
port state, traffic and errors, MAC tables, ARP, LLDP and CDP neighbours, CPU, memory and temperature, a
firewall's gateways and states. [Telegraf](https://www.influxdata.com/time-series-platform/telegraf/)
does the collecting; Floorbit tells it what to ask and keeps what comes back.

LibreNMS stays a choice: the **Telemetry** plugin is one more monitoring source next to LibreNMS,
Prometheus, Zabbix and the rest (Settings > Plugins). Only one answers at a time; see
[Who polls the switches](#who-polls-the-switches) for how Telemetry and LibreNMS share the work, and
[Network segments](segments.md) for the VLANs where check-ins may look PCs up.

## Who polls the switches

When LibreNMS runs, it polls the switches anyway. Telemetry polling the same ports and walking the
same ARP and MAC tables would only double the load on the access switches, so the Telemetry
setting **Who polls the switches** decides:

| Setting | Ports and ARP/MAC tables | Telemetry still does |
| --- | --- | --- |
| **Auto** (default) | LibreNMS when its plugin is on with a URL and token, else Telemetry | traps, device facts, gNMI/MDT streams, the API pollers |
| **LibreNMS** | LibreNMS, even before it is set up | the same |
| **Telemetry** | Telemetry, and it answers before LibreNMS | everything |

Traps stay with Telemetry either way: they turn a port down or up within a second, while LibreNMS
sees it on its next 5-minute poll. The device facts (model, software, interfaces) keep filling the
inventory ([discovery](inventory.md)).

With the ports Telemetry also reads the temperatures: CISCO-ENVMON-MIB on Catalyst and IOS-XE,
ENTITY-SENSOR-MIB (the celsius sensors) on Nexus and others. A switch's status gives the hottest
sensor heard in the last 3 minutes as `temperature`, in degrees C, where LibreNMS gives its sensors'
average. Until a switch's first port poll is in, its status says `unknown` with `waiting: true`
instead of counting only the ports a trap or a stream has named so far.

When Telemetry polls, it walks the ARP and MAC tables every **ARP and MAC tables every (minutes)**
(0: never). **Auto** (the default) walks them every 15 minutes while a [network segment](segments.md)
has lookups on, because check-ins then ask the switches for their one PC, and every minute otherwise. When the chosen source doesn't know an IP, Floorbit asks the other
monitoring source before giving up, and the answer says which one gave it (`answered_by`). The
agent's log says who polls whenever that changes:

```
[telemetry] polling: LibreNMS polls ports and ARP/MAC tables (LibreNMS is on); here: traps, device facts and streams
```

## How it fits together

```
switches, firewalls ──SNMP, gNMI, traps, MDT──▶ Telegraf ──line protocol──▶ collector ──▶ storage
                     ◀──NX-API, RESTCONF, OPNsense API── collector
```

The **collector** is Floorbit itself when you host it yourself, or the
[local agent](agent.md) when Floorbit is hosted. It keeps the latest picture of every device in
memory (what the floor plan, the seat inspector, check-in and the topology read), and stores the
history (see [Storage](#storage)).

## Set it up

Devices are set up in the [inventory](inventory.md), nowhere else: the **Telemetry** tab of a
device, a group, a tag or **All devices**. The **Telemetry** page under Monitoring shows what comes
in from each device (find and filter by problems or never heard), the collector's state on its
**Collector** tab and the ingest token on **Senders**; each device opens its own Telemetry tab.

1. **The inventory**: turn the **Telemetry** feature on for a device, a tag, a group or a type, and
   store its logins there: SNMP v3 (or v2c) for polling and traps, and an API login for NX-API
   (NX-OS), RESTCONF (IOS-XE) or the OPNsense API. See [Devices from the inventory](#devices-from-the-inventory)
   for the properties that say more. The ways to collect:

    | Way | For | Notes |
    | --- | --- | --- |
    | SNMP polling | everything | IF-MIB ports every 30 s; ARP, MAC tables, LLDP and CDP every 60 s. v2c or v3. |
    | SNMP traps | everything | linkUp/linkDown change a port at once, between polls. |
    | gNMI | NX-OS 9.3+, IOS-XE 16.12+ | OpenConfig interfaces, streamed every 10 s and on change. |
    | Cisco MDT dial-out | NX-OS, IOS-XE 16+ | The device connects to the collector (port 57000, gRPC). |
    | NX-API | Nexus | `show ip arp vrf all` and `show interface` over HTTPS. The Nexus core holds the ARP table. |
    | RESTCONF | IOS-XE 16+ | ARP and interfaces, the same YANG models MDT streams. |
    | OPNsense API | OPNsense | Gateways (up, delay, loss), ARP, interface counters. A key with the Diagnostics and Status privileges only. |
    | Own Telegraf | OPNsense, pfSense | The firewall runs Telegraf (OPNsense `os-telegraf`, the pfSense Telegraf package) and sends to the collector. |

    A device that only sends by itself (`telemetry.drivers` of `push`, `mdt` or `traps`) needs no
    login. **Device setup** on the device's Telemetry tab shows what to paste on the device for traps, MDT,
    gNMI, NX-API and RESTCONF.

2. **Catalyst IOS (2960-X, 4500 on IOS-XE 3.x)** answers MAC tables one VLAN at a time. That is
   the default on IOS; Floorbit reads the VLANs the switch lists itself (discovery's VTP walk, without
   the reserved 1002 to 1005), else the VLANs on its interfaces, or the ones listed in
   `telemetry.snmp.vlans`. Floorbit then asks `community@vlan` (v2c) or the
   `vlan-<id>` context (v3). A VLAN the switch doesn't have gets no answer at all, so each VLAN is
   its own poll and a problem names it ("no answer for VLAN 30"). Nexus and IOS-XE 16+ answer Q-BRIDGE in one table.

3. **Telegraf.** The local agent runs it: it is in the agent image, and the Telemetry plugin starts
   it, writes its config from the inventory's devices and reloads it when they change (agent.md,
   ["Telegraf"](agent.md#telegraf)). Nothing to start. Publish udp/162 (traps) and tcp/57000 (MDT)
   on the agent machine if the devices send (the agent's compose file does). The Local agents page
   shows how the collector is doing (points, devices heard, which devices fail and why).
    - Kubernetes: see [`deploy/kubernetes/telemetry.yaml`](https://github.com/bitsandbricks-ch/floorbit/blob/master/deploy/kubernetes/telemetry.yaml).
    - Your own Telegraf: **Download telegraf.conf** and point its HTTP output at Floorbit.

4. **Settings > Plugins**: turn on **Telemetry**. If LibreNMS is set up too, LibreNMS still wins
   (plugins are tried in id order); clear LibreNMS's URL to switch.

## When a device sends nothing

The agent reads every line Telegraf prints and every error of the API pollers, and keeps the current
problem per device and kind of collection. The Telemetry page and the device's Telemetry tab show it, the
agent's page names the first one, and the agent's log has each new one with the device's name.

| Says | What it means | What to check |
| --- | --- | --- |
| Nothing listens on *address* | The device answered "port closed" (ICMP port unreachable, TCP reset) | SNMP, gNMI or the API is off on the device, listens on another port, or only on another address (`snmp-server` on a management VRF) |
| No answer from *address* | Nothing came back in time | For SNMP a wrong community or SNMPv3 login looks exactly like this (the device stays silent), as does an ACL that doesn't list the agent's address; for the others, a firewall on the way |
| No answer for VLAN *n* | The switch answers SNMP, but not `community@n` (or the `vlan-n` context) | The switch doesn't have that VLAN (fix `telemetry.snmp.vlans`), or with SNMPv3 the user's group doesn't allow the `vlan-` contexts |
| No answer while reading *table* | A table walk timed out | If the device's other data comes in, the walk is too slow: a very big table, or SNMP rate limited on the device. If nothing comes in, as "No answer" above |
| Refused the login | The device said no to the user, password, SNMPv3 keys or API key | The login on the device or in Floorbit; refused logins aren't tried again until cleared (agent-plugins.md, "Failed logins") |
| No route to *address* | The agent's machine can't reach that network | The address, and the agent machine's routes or VLAN |
| TLS failed | The certificate didn't check out | The device's certificate, or turn off **Check TLS** for it |
| Cannot open its listening port | Telegraf can't take traps or MDT | Another program holds the port in the container, or an old telegraf container still runs |

A problem goes away when the device sends again, or after three minutes without the error. One
VLAN's or one table's problem only goes away by not coming back, since the device's other data keeps
coming in. Such a device doesn't count as failing: the agent's health says "answer only in part"
instead. A device that only sends traps isn't listed as silent when a minute passes without one.

**Test now** collects from one device once, through the agent, and shows what came back or the exact
error; **Raw data** shows the last lines Telegraf sent for it. On the agent machine,
`docker compose exec agent telegraf --config /app/state/plugins/telemetry/own-telegraf/telegraf.conf --test`
does the same for every device.

## Devices from the inventory

Turn the **Telemetry** feature on for a device, a tag, a group or a type, and store its logins
there: SNMP v3 (or v2c) for polling and traps, and an API login for NX-API (NX-OS), RESTCONF
(IOS-XE) or the OPNsense API.

What it does follows the device's software (its platform) and the logins it finds, unless
something says otherwise:

- **Ways to collect:** SNMP polling and traps with an SNMP login, plus the platform's API with an
  API login (NX-API on NX-OS, RESTCONF on IOS-XE, the OPNsense API). Cisco MDT, gNMI and a
  firewall's own Telegraf need setting up on the device first, so they are never on by themselves:
  choose them.
- **MAC tables:** per VLAN on Cisco IOS and IOS-XE, the standard Q-BRIDGE table otherwise.
- **VLANs to read:** the VLANs on the device's interfaces.
- **MDT node name:** the device's own name.

The **Telemetry** tab of a device, a group, a tag or All devices sets all of it without typing
property names: on, off or inherit; **Automatic** or **Choose** the ways to collect; MAC tables,
VLANs, the MDT node, the agent, the address and the ports. An empty field shows what applies and
where it comes from. A device's tab also shows its last word, **Test now**, **Raw data** and
**Device setup**. The tab writes these properties, which a type can set too. They sit under
`telemetry.` like the property levels (inventory.md, "Properties in three levels"); the older names
without the namespace (`telemetry_vlans`, `telemetry_port_snmp`, ...) are moved once when Floorbit starts.

| Property | What |
| --- | --- |
| `telemetry.drivers` | the ways to collect, like `snmp, traps, gnmi` (instead of the automatic ones) |
| `telemetry.snmp.fdb` | MAC tables: `qbridge`, `cisco_vlans` (Catalyst IOS, the default there), `bridge`, `off` |
| `telemetry.snmp.vlans` | the VLANs to read MAC tables from per VLAN, like `10, 20` (default: the VLANs the switch lists, else the ones on its interfaces) |
| `telemetry.agent` | the local agent that collects from it (its id; the Telemetry tab picks it by name) |
| `telemetry.snmp.port`, `telemetry.gnmi.port`, `telemetry.api.port` | a port per way of asking, when not the usual one (161; 50051 on NX-OS, 9339 on IOS-XE; 443) |
| `telemetry.address` | where the agent reaches the device, when not its management address |
| `telemetry.api.url` | the API's full `https://` address |
| `telemetry.mdt.node` | the node name a device sends model-driven telemetry as (default: its name) |
| `telemetry.verify_tls` | `false` for an API with a self-signed certificate |

Every five minutes SNMP polling also asks what the device is (sysDescr, sysLocation, the chassis
model and serial and the optics from ENTITY-MIB, memory and disks from HOST-RESOURCES-MIB, the Cisco memory pool,
which also gives the memory use), and per port its MAC, IPv4 addresses, VLAN and access or trunk
mode, with the device's VLAN names. [Discovery](inventory.md#discovery) fills the inventory device
from it.

Firewalls also say their **routes** every five minutes (IP-FORWARD-MIB ipCidrRouteTable: network,
next hop, interface and where it came from: connected, static, OSPF, BGP, ...), up to 2,000 per
firewall. Routers aren't asked: an internet router's full table is far too big to walk.

With the tables (every minute), switches also say their **PoE** (POWER-ETHERNET-MIB): per port
whether it is off, searching, delivering (with the class) or in fault, and on Cisco what it draws
and what is set aside for it (CISCO-POWER-ETHERNET-EXT-MIB, `draw_w` and `allocated_w`), and per
switch the budget and what it gives now. Cisco names each PoE row's port through ENTITY-MIB; on
other switches with one PoE group the port number is the ifIndex. Each port's `poe` is in the
device's ports (`device_ports`), and the switch's budget in discovery's `discovered.poe`.

A login the device refuses is blocked on the inventory device, like any stored login: it isn't
tried again until a tech clears it or the password changes.

## Wireless controllers

### Catalyst 9800

A Catalyst 9800 (the 9800-CL VM or the appliances) streams its access points over the same MDT
dial-out as the switches, and the [Wi-Fi view](wifi.md) shows them: each AP up or down, and per
radio its band, channel, width, channel utilization and client count, every 30 seconds.

1. Add the controller to the inventory with platform **IOS-XE** and its model (`C9800-CL-K9`,
   `C9800-40-K9`, ...): the model tells Floorbit it is a wireless controller. Turn the Telemetry
   feature on and choose **MDT** as the way to collect.
2. Paste **Device setup** from its Telemetry tab on the controller. Besides the interfaces it
   subscribes to three paths, every 30 seconds:

   | Path | What Floorbit takes |
   | --- | --- |
   | `/wireless-access-point-oper:access-point-oper-data/capwap-data` | each joined AP: name, model, joined or not |
   | `/wireless-access-point-oper:access-point-oper-data/radio-oper-data` | each radio: band, channel, width, on or off |
   | `/wireless-rrm-oper:rrm-oper-data/rrm-measurement` | each radio: channel utilization, clients |

   ```
   telemetry ietf subscription 102
    encoding encode-kvgpb
    filter xpath /wireless-access-point-oper:access-point-oper-data/capwap-data
    stream yang-push
    update-policy periodic 3000
    receiver ip address 192.0.2.10 57000 protocol grpc-tcp
   ```

### AireOS (5520, 3504, 8540)

An AireOS controller answers its access points over SNMP (AIRESPACE-WIRELESS-MIB). Add it to the
inventory with its model (`AIR-CT5520-K9`, ...) and an SNMP login, and turn the Telemetry feature
on. Every minute Telemetry reads three tables: the APs (`bsnAPTable`: name, model, joined), their
radios (`bsnAPIfTable`: band, channel, on or off) and the radios' load (`bsnAPIfLoadParametersTable`:
channel utilization, clients). It does this even while [LibreNMS polls](#who-polls-the-switches):
LibreNMS reads the same tables but has no API for them. The client table (`bsnMobileStationTable`)
is never asked for.

### Both

Every 30 seconds the controller's numbers are stored with the rest of the telemetry: `wifi_clients`
on the controller, and per AP (as its `port`) `clients` and `utilization` (its busiest radio). The
[Wi-Fi view](wifi.md) draws clients over time from them, and `GET /api/telemetry/series` reads any of
them.

An AP the controller stops naming reads **down** after three minutes and leaves the list after a
day. When a Wi-Fi plugin (Cisco WLC, UniFi, ...) names the same AP, the stream wins.

The controller's client list is never subscribed to. Should a controller stream one anyway (a
`client-oper` path), it is neither understood nor stored.

<!-- TODO(Mike): checked against the YANG models only; confirm the field names on a live 9800-CL
with "Raw data" before the first event (docs: floorbit-wlc-telemetry). -->

## Two agents (VRRP)

With two or more local agents sharing virtual IPs (the agent's `docs/vrrp.md`, active/passive or
active/active), only one collects: the agent that holds the **first** VIP. It runs Telegraf's
polling (SNMP, gNMI) and the NX-API, RESTCONF and OPNsense pollers, and sends the numbers and the
IP and MAC history. The others write a Telegraf config with the listeners only, answer nothing
about the devices, and send nothing. So a device is never polled or logged into by two agents,
and the hosted Floorbit gets each minute once. When the first VIP moves, the agent that now holds
it starts collecting within about 5 seconds; its picture fills within a polling round.

Point the devices' traps, model-driven telemetry and a firewall's own Telegraf at the first VIP.

Nothing comes in twice on the hosted side either:

- Floorbit asks every connected agent and keeps the answer that has something, the device and
  ARP lists merged once.
- What an agent kept on its disk while the link was down keeps its own time (up to 6 hours back).
  A batch older than what is known, or the same batch from a second agent, adds no history row.
  The lite rollups keep one value per series and minute.
- VictoriaMetrics runs with `-dedup.minScrapeInterval=30s` in the compose file and the k3s
  manifest, so a point written twice is kept once.


## One agent per device

A device with an agent (`telemetry.agent`, the Telemetry tab) is collected by that agent alone, even
when it stands by for another one, and calls about the device (its ports, its clients) go there.
Give a hall's group its hall's agent, and each agent polls only its own switches. While that agent
is away, its devices go back to the others like devices without an agent, so they aren't left
unheard. Devices without an agent are collected as above: by the agent with the first VIP.

## Firewalls: pfSense and OPNsense

Neither does model-driven streaming. What comes closest:

- **Their own Telegraf** every 10 s: in the firewall's Telegraf settings, add an InfluxDB output
  to `https://<floorbit>/api/telemetry` with the token from the Telemetry page (admins): as the token for
  InfluxDB v2, or as the password for v1. With a local agent, point it at `https://<agent>:8186`
  instead (plain `http://` when the agent has no certificate: set `FLOORBIT_AGENT_TLS_CERT` and
  `FLOORBIT_AGENT_TLS_KEY` on the agent), with the agent's own token (the `ingest-token` file in the agent's
  `plugins/telemetry` state folder). CPU, memory, interfaces and
  `pf` states arrive with the firewall in the `host` tag; name the device the same on the
  Telemetry page.
- **NetFlow** (OPNsense's built-in NetFlow, pfSense's softflowd package) to the flow collector
  ([flows.md](flows.md)): aggregated before it leaves the hall.
- **Remote syslog** (the filter log) to [syslog](syslog.md).
- **The OPNsense API** for gateways and ARP. pfSense has no built-in API: Telegraf and SNMP there.

## Storage

- **Lite** (the default): Floorbit's own database keeps a normalised series per device and port:
  a point a minute for 6 hours and every 15 minutes for `FLOORBIT_TELEMETRY_DAYS` (2 days).
- **VictoriaMetrics**: `docker compose --profile metrics up -d` and
  `FLOORBIT_VICTORIAMETRICS_URL=http://victoriametrics:8428`. Every point that came in is kept, plus
  the normalised series (`fb_port_in_bps_value{device,port}`, `fb_port_out_bps_value`,
  `fb_port_errors_value`, `fb_port_up_value`, `fb_device_up_value`, `fb_device_cpu_value`,
  `fb_device_mem_value`, `fb_device_states_value`), for as long as its `-retentionPeriod` says.
- Logs aren't telemetry: to keep the syslog longer, start VictoriaLogs with `--profile logs` and turn on
  its plugin ([syslog.md](syslog.md#keeping-it-longer-victorialogs-or-grafana-loki)).
- **Grafana** (`--profile grafana`): add VictoriaMetrics as a Prometheus data source.

Redis isn't used for telemetry.

`GET /api/telemetry/series?device=sw-a-01&port=Gi1/0/1&metric=in_bps&hours=6` answers one series
from whichever storage is in use.

## Privacy

MAC tables, ARP and neighbour tables name the machines at the seats. They are never written into
the telemetry series or sent to VictoriaMetrics. Where each machine was seen (MAC, IP, port, seat)
goes into the [IP and MAC history](endpoints.md) instead, kept for 7 days and shown only to roles
that may see who sits where. With a local agent, the agent sends that history to the hosted
Floorbit once a minute; live lookups (which port is this IP on?) still ask the agent.

## Secrets

Communities, SNMPv3 passphrases, gNMI, NX-API, RESTCONF logins and OPNsense API secrets are
encrypted with Floorbit's key ([credentials.md](credentials.md)) and never come back to a browser.
They are opened only to write Telegraf's config (a file only Floorbit's user can read) or to send
to an enrolled agent over its TLS link, as the Telemetry plugin's settings. Use read-only
accounts on the devices.

## Security

- **SNMP:** v2c sends the community in clear text and its traps can be faked; use SNMPv3 with
  authPriv (SHA/AES, the default for v3) wherever the devices allow it.
- **Traps and Cisco MDT** carry no token, so Floorbit only takes them from a device set up here
  with that address (or MDT node name). Anything else is counted as unknown and dropped.
- **A wireless controller's client list** (`client-oper` paths) is dropped before storage, whatever
  alias it comes under.
- **Cisco MDT over TLS:** plain gRPC lets anyone on the management network send counters. Give
  Telegraf a certificate (`FLOORBIT_TELEGRAF_MDT_CERT`, `FLOORBIT_TELEGRAF_MDT_KEY`, paths as
  Telegraf sees them, and `FLOORBIT_TELEGRAF_MDT_CA` to take only devices with a certificate from
  your CA) and it takes MDT over TLS only; **Device setup** then shows `grpc-tls`.
- **The ingest token** goes in the `Authorization` header (InfluxDB v2 `Token`, or the v1
  password), never in the URL, where proxies log it.

When a device refuses a login (NX-API, RESTCONF, the OPNsense API key), the collector stops trying
that device with it: no account lockouts, no alarms on the AAA server. Change the login in the
inventory and it is tried again; on a local agent, **Clear, try again** on the Local
agents page does it too. Not even a restart tries the old login again.

## Extending it

Plugins can teach the collector new devices:

- `floorbit.telemetry.pollers.register('mydriver', poll)`: `poll(target, now)` returns
  `lineproto.Point`s; the driver then shows on the Telemetry page.
- `floorbit.telemetry.state.register('measurement', handler, private=False)`:
  `handler(device, point, at)` updates the device's picture. `private=True` keeps the measurement
  out of storage.

## Watching the collector

`GET /api/telemetry/status`: where it collects, devices, points received and not understood,
storage mode and errors, and the last error per device. The Telemetry page shows the same, and
each device's last report.

The **Telemetry devices** widget (a dashboard tile, from the plugin) lists each device as up when
it reported in the last minutes, with a link to the Telemetry page. On a hosted Floorbit it asks
the local agent.

### In the agent's log

Every telemetry line in the agent's log carries a topic after the plugin's tag, so you can keep one
kind with `grep '\[telemetry\] \[traps\]'` (or `docker compose logs agent | grep ...`):

| Topic | What it says |
| --- | --- |
| `[settings]` | the devices Floorbit sent (names only, never logins) and who polls the switches |
| `[telegraf]` | Telegraf starting, stopping, reloading its config, and its own warnings |
| `[devices]` | a device first heard, gone silent, and the summary every few minutes |
| `[snmp]` | the poll line every minute: points per device, and the devices that sent nothing |
| `[traps]` | each trap as it comes in: the device, the trap and its port |
| `[stream]` | gNMI and Cisco MDT: one line a minute with the points per device |
| `[api]` | the API pollers (firewalls, controllers) |
| `[push]` | each send to Floorbit: the series and the IP and MAC sightings, with how many parts |
| `[test]` | **Test now** runs |
| `[role]` | the agent becoming the collector or standing by (VRRP) |
| `[lookup]` | a check-in asking the switches for one PC, and what it found |

These lines are at info level. `FLOORBIT_AGENT_LOG_LEVEL=debug` adds Telegraf's chatter and the
details behind each line.
