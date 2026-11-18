# Device telemetry

Floorbit can hear from the hall's switches, routers and firewalls directly, without LibreNMS:
port state, traffic and errors, MAC tables, ARP, LLDP and CDP neighbours, CPU and memory, a
firewall's gateways and states. [Telegraf](https://www.influxdata.com/time-series-platform/telegraf/)
does the collecting; Floorbit tells it what to ask and keeps what comes back.

LibreNMS stays a choice: the **Telemetry** plugin is one more monitoring source next to LibreNMS,
Prometheus, Zabbix and the rest (Settings > Plugins). Only one is used at a time.

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

1. **Settings > Telemetry**: add each device. Pick it from the floor plan's switches or firewalls,
   give its management address, its platform and how to collect from it:

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

    **Device setup** shows what to paste on the device for traps, MDT, gNMI, NX-API and RESTCONF.

2. **Catalyst IOS (2960-X, 4500 on IOS-XE 3.x)** answers MAC tables one VLAN at a time. Pick
   *MAC tables: Per VLAN* and list the seat VLANs. Floorbit then asks `community@vlan` (v2c) or the
   `vlan-<id>` context (v3). Nexus and IOS-XE 16+ answer Q-BRIDGE in one table.

3. **Start Telegraf.**
    - Self-hosted with Docker: `docker compose --profile telemetry up -d`. Floorbit writes
      `/app/state/telegraf/telegraf.conf` and Telegraf reloads it when the devices change. Publish
      udp/162 (traps) and tcp/57000 (MDT) to the machine if the devices send.
    - Kubernetes: see [`deploy/kubernetes/telemetry.yaml`](https://github.com/bitsandbricks-ch/floorbit/blob/master/deploy/kubernetes/telemetry.yaml).
    - Hosted with a local agent: the Telemetry plugin's agent part is the collector. Run Telegraf
      next to the agent (`docker compose --profile telemetry up -d` in the agent's folder); the
      agent writes its config into the shared state volume and takes its line protocol on port
      8186. Monitoring calls through the agent are answered from what the devices sent (leave
      LibreNMS unset on the agent). The Local agents page shows how the collector is doing (points,
      devices heard, errors, whether Telegraf is quiet).
    - Your own Telegraf: **Download telegraf.conf** and point its HTTP output at Floorbit.

4. **Settings > Plugins**: turn on **Telemetry**. If LibreNMS is set up too, LibreNMS still wins
   (plugins are tried in id order); clear LibreNMS's URL to switch.

## Devices from the inventory

Devices already in the inventory don't need setting up twice. Turn the **Telemetry** feature on
for a device, a tag, a group or a type, and store its logins there: SNMP v3 (or v2c) for polling
and traps, and an API login for NX-API (NX-OS), RESTCONF (IOS-XE) or the OPNsense API. Floorbit
then collects from it like from a device on Settings > Telemetry, which lists these under "From
the inventory".

What it does follows the platform and the logins it finds: SNMP polling and traps with an SNMP
login, plus the platform's API with an API login. Properties on the device (or inherited) can say
more:

| Property | What |
| --- | --- |
| `telemetry_drivers` | the ways to collect, like `snmp, traps, gnmi` (overrides the guess) |
| `telemetry_fdb` | MAC tables: `qbridge`, `cisco_vlans` (Catalyst IOS, the default there), `bridge`, `off` |
| `telemetry_vlans` | the VLANs to read MAC tables from per VLAN, like `10, 20` |
| `telemetry_port`, `telemetry_url` | the API's port, or its full `https://` address |
| `telemetry_mdt_node` | the node name a device sends model-driven telemetry as |
| `telemetry_verify_tls` | `false` for an API with a self-signed certificate |

A login the device refuses is blocked on the inventory device, like any stored login: it isn't
tried again until a tech clears it or the password changes. A device set up on Settings >
Telemetry by the same name wins over the inventory's.

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

## Firewalls: pfSense and OPNsense

Neither does model-driven streaming. What comes closest:

- **Their own Telegraf** every 10 s: in the firewall's Telegraf settings, add an InfluxDB output
  to `https://<floorbit>/api/telemetry` with the token from Settings > Telemetry: as the token for
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
- **VictoriaLogs** for log events: `--profile logs` and `FLOORBIT_VICTORIALOGS_URL=http://victorialogs:9428`.
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
- **Cisco MDT over TLS:** plain gRPC lets anyone on the management network send counters. Give
  Telegraf a certificate (`FLOORBIT_TELEGRAF_MDT_CERT`, `FLOORBIT_TELEGRAF_MDT_KEY`, paths as
  Telegraf sees them, and `FLOORBIT_TELEGRAF_MDT_CA` to take only devices with a certificate from
  your CA) and it takes MDT over TLS only; **Device setup** then shows `grpc-tls`.
- **The ingest token** goes in the `Authorization` header (InfluxDB v2 `Token`, or the v1
  password), never in the URL, where proxies log it.

When a device refuses a login (NX-API, RESTCONF, the OPNsense API key), the collector stops trying
that device with it: no account lockouts, no alarms on the AAA server. Change the login on
Settings > Telemetry and it is tried again; on a local agent, **Clear, try again** on the Local
agents page does it too. Not even a restart tries the old login again.

## Extending it

Plugins can teach the collector new devices:

- `floorbit.telemetry.pollers.register('mydriver', poll)`: `poll(target, now)` returns
  `lineproto.Point`s; the driver then shows on Settings > Telemetry.
- `floorbit.telemetry.state.register('measurement', handler, private=False)`:
  `handler(device, point, at)` updates the device's picture. `private=True` keeps the measurement
  out of storage.

## Watching the collector

`GET /api/telemetry/status`: where it collects, devices, points received and not understood,
storage mode and errors, and the last error per device. Settings > Telemetry shows the same, and
each device's last report.

The **Telemetry devices** widget (a dashboard tile, from the plugin) lists each device as up when
it reported in the last minutes, with a link to Settings > Telemetry. On a hosted Floorbit it asks
the local agent.
