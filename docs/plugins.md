# Plugins

Plugins add things to Floorbit without changing its core: buttons that run code (actions), tiles on
the dashboard (widgets), read-only JSON (endpoints) and code that runs when something changes
(hooks). The design is borrowed from labdex (manifest, `Plugin` class, widgets as data) and Hubra
(`uses:`: a plugin can touch only the areas it lists).

## Turning plugins on

Settings > Plugins lists every plugin, what it may touch, and whether it is on. Plugins start
**off**, except the few that ship with Floorbit and replace what used to be built in (NetBox); those
start on and do nothing until they're configured. Turning one on or off is in the audit log. A plugin's settings are on the settings page,
in a section called *Plugin: <name>*. Secrets are write-only there, as everywhere.

The **Dashboard** (top bar of the floor plan, `/dashboard`) shows the tiles of the plugins that are
on, for anyone signed in whose role is allowed to see them.

Where plugins come from:

| Trust | Where | Notes |
| --- | --- | --- |
| Ships with Floorbit | `floorbit/builtin_plugins/` | Reviewed with Floorbit itself. |
| Development checkout | the folder in `FLOORBIT_DEV_PLUGINS` | For writing plugins. **Never set it in production**: the code runs inside Floorbit. |

Installing other plugins (signed releases that run in a locked-down process of their own, like
labdex's community plugins) comes in a later step. Until then, no outside code runs.

Which plugins are on, and each plugin's small private state, live in `plugins.json` next to
`data.json`, or wherever `PLUGINS_FILE` points (Compose: the `state` volume).

## Built in: NetBox

Feeds the [inventory](inventory.md) with the NetBox devices that have the configured roles: name,
role, model, serial, management IP, site or location, and status. It is on by default and uses the
settings under **Settings > NetBox** (`NETBOX_URL`, `NETBOX_TOKEN`, `NETBOX_DEVICE_ROLES`,
`NETBOX_VERIFY_SSL`), as before it became a plugin. It only reads from NetBox and only follows
NetBox's "next page" links to the same host. Run it with **Sync now** on the Inventory page or the
sync button on the floor plan.

## Built in: LibreNMS

The monitoring source: live switch status, port details and traffic, and which switch port an IP
or MAC is on (ARP, then the MAC tables). The floor plan, the seat heatmap, the status monitor and
the check-in page all get their live data from it. It is on by default and uses the settings
under **Settings > LibreNMS** (`LIBRENMS_URL`, `LIBRENMS_TOKEN`, `LIBRENMS_VERIFY_SSL`,
`LIBRENMS_FDB_EXCLUDE`), as before it became a plugin. Turn it off and the floor plan shows every
switch as unknown. Only one monitoring plugin is used at a time: demo data when it is on, then
the first one that is on and set up (so turning on Prometheus is enough while LibreNMS has no URL).

## Built in: Prometheus

For halls that scrape their switches with the SNMP exporter instead of running LibreNMS (#39). Off
until an admin turns it on under **Settings > Plugins**. It reads the `if_mib` series of one scrape
job:

| Floorbit needs | From |
| --- | --- |
| Is the switch reachable | `up` |
| Port up, down or disabled | `ifOperStatus`, `ifAdminStatus` |
| Speed | `ifHighSpeed` |
| Traffic | `rate(ifHCInOctets[…])`, `rate(ifHCOutOctets[…])` |
| Errors | `ifInErrors`, `ifOutErrors` and their rates |
| Port name and description | the `ifName` (or `ifDescr`) and `ifAlias` labels |

Settings:

- **URL:** Thanos and VictoriaMetrics work too.
- **Bearer token:** optional.
- **Job:** default `snmp`.
- **Switch name label:** default `instance`. It has to match the switch names on the floor plan.
- **Rate window:** default `2m`. Make it at least twice the scrape interval.

Switch names are quoted and escaped in every query, and the label and job settings are checked, so
nothing typed on the floor plan can change a query.

Prometheus keeps no ARP or MAC tables. Finding which port an IP is on (the check-in page, a seat's
port) needs a seat source or the seat mapping.

## Built in: UniFi

For halls built from UniFi switches (#39). Off until an admin turns it on under **Settings >
Plugins**. It reads the UniFi Network controller's own API and needs a local account with the
**View Only** role. It signs in for each read and signs out again.

| Floorbit needs | From |
| --- | --- |
| Is the switch online | `stat/device`: `state` (switches only, `type` `usw`) |
| CPU, memory, temperature | `system-stats`, `general_temperature` |
| Port state, speed, duplex, traffic, errors | the switch's `port_table` |
| Which port an IP or MAC is on | `stat/sta`: the client's `sw_mac` and `sw_port` |

UniFi calls a port "Port 7". A name given to it in the controller, like "Seat A1", becomes the
port's description, and the seat inspector finds the port by either. Players on Wi-Fi have no switch
port.

Settings:

- **Controller URL:** the console or the Network application, with no path.
- **UniFi OS console:** on for a Dream Machine, a Cloud Key Gen2 or a UniFi OS server; off for the
  older Network application on port 8443.
- **Username and password:** the View Only account.
- **Site:** the short name from the controller's URL. Default `default`.
- **Verify TLS:** consoles ship with a self-signed certificate. Turn this off only on a network you
  trust.

## Built in: MikroTik

For MikroTik switches and routers running RouterOS 7 (#39). Off until an admin turns it on under
**Settings > Plugins**. Each device is its own API, so the plugin lists them as `Name=URL`, for
example `sw-a-01=https://192.0.2.21`. The names must match the floor plan. Add the router too, so
its ARP table can be searched.

| Floorbit needs | From |
| --- | --- |
| Is the switch answering, CPU and memory | `/rest/system/resource` |
| Ports: state, disabled, comment, error counters | `/rest/interface` (Ethernet ports only) |
| Traffic | `interface/monitor-traffic` (once) |
| Link speed and duplex | `interface/ethernet/monitor` (once) |
| Which port an IP is on | `/rest/ip/arp` on every listed device, then `/rest/interface/bridge/host` |

When the player's MAC shows up on several switches, the access port wins. Ports whose comment
matches the uplink pattern (`STATS_UPLINK_PATTERN`, default `uplink|trunk`) are skipped, so comment
your uplinks.

Use an account in a group with only `read` and `api` (or `rest-api`) rights. The only POSTs are the
two monitor commands, and they change nothing. Devices are asked in parallel, 16 at a time. A
device that doesn't answer within the timeout reads as offline, and the plugin's log says why.
RouterOS serves the REST API over its `www-ssl` service, which needs a certificate.

## Built in: Zabbix

For halls that already watch their switches in Zabbix (#39). Off until an admin turns it on under
**Settings > Plugins**. It calls the front end's JSON-RPC API (`api_jsonrpc.php`, Zabbix 6.4 or
newer) with an API token, and only uses `*.get` methods.

| Floorbit needs | From |
| --- | --- |
| Switches | `host.get` for the hosts in one host group (default `Switches`) |
| Reachable or not | the availability of the host's SNMP interface |
| Port state, traffic, speed, errors | `item.get`: the `net.if.status`, `net.if.in`, `net.if.out`, `net.if.speed`, `net.if.in.errors` and `net.if.out.errors` items that Zabbix's SNMP templates create for each discovered port |

The port name and description come from the item names ("Interface Gi1/0/1(Seat A1): ...").
Hosts that are not monitored in Zabbix read as unknown. Zabbix keeps no ARP or MAC tables, so
finding which port an IP is on needs another source.

Create the token for a user whose role can only read the switches' host group.

## Built in: Aruba AOS-CX

For halls with Aruba CX switches (#39). Off until an admin turns it on under **Settings > Plugins**.
Every switch is listed as `Name=https://address`; Floorbit talks to each switch's REST API
(`/rest/v10.08`, AOS-CX 10.08 or newer) and only reads.

| Floorbit needs | From |
| --- | --- |
| Reachable or not | `GET system` answers |
| Port state, speed, duplex, traffic, errors | `GET system/interfaces?depth=2` (physical ports only, not VLAN interfaces or LAGs) |
| Which port an IP is on | the ARP table in `system/vrfs/default/neighbors` on any listed switch, then the MAC in `system/vlans/<id>/macs` on each switch. Ports whose description matches the uplink pattern are skipped, so the access port wins over the core's uplink |

Each read signs in and signs out again, because AOS-CX allows only a few sessions per user and a
poll that kept them open would lock the account out. Give Floorbit a local user with the
read-only `operators` group. **VLANs** limits the MAC lookup to the seat VLANs; without it every
VLAN on the switch is asked, which takes longer on big switches.

## Built in: AdGuard Home

Reads AdGuard Home's query log for [DNS analytics](dns.md). Turn it on under Settings > Plugins and
set the URL of its web interface (for example `http://dns.example.com:3000`), a username and a
password. The query log must be on in AdGuard Home. Floorbit reads `GET /control/querylog` back to
where it was the last time, at most 10,000 lookups a poll, and counts as blocked what AdGuard
filtered by a block list, safe browsing, parental control or a blocked service. Rewrites and safe
search are not blocks.

## Built in: Pi-hole

Reads Pi-hole's query log (Pi-hole 6 and newer) for [DNS analytics](dns.md). Set the URL of its web
interface (without `/admin`) and an app password (Settings > Web interface / API in Pi-hole). Each
poll signs in, reads `GET /api/queries` since the last poll (at most 20,000 lookups) and signs out
again, because Pi-hole allows only a few sessions at once. Lookups blocked by gravity, regex or deny
lists, or blocked upstream, count as blocked.

## Built in: Grafana Loki

Keeps the [syslog](syslog.md) longer than Floorbit's own 24 hours. Set Loki's URL (for example
`http://loki.example.com:3100`), and the tenant, username and password when your Loki needs them
(the tenant is sent as `X-Scope-OrgID`). Every 10 seconds Floorbit pushes the new lines to
`/loki/api/v1/push` with a few labels (`job="floorbit"`, `source="syslog"`, `device`, `severity`, and
`event` when the **Event label** is set); the rest of a line is JSON, so `| json` gets `program`,
`message`, `port` and `seat`. Lines Loki didn't take are sent again next time. The Logs page then
gets a **Grafana Loki** source to search it with LogQL, over up to 30 days.

## Built in: Demo data

A made-up hall for trying Floorbit without a network: inventory, seat mapping and live data (it
replaces LibreNMS while it's on). Off unless `FLOORBIT_DEMO=1` or an admin turns it on. See
[demo.md](demo.md).

## Built in: HTTP check

Checks that web services answer (the LAN cache, the ticket shop, a game server's web panel) and
shows them as a status tile. Settings: the services (`Name=URL`, comma separated), a timeout, and
whether to verify TLS. Editors can run **Check now**; the tile checks again when its results are
older than a minute. Redirects are not followed, so a service that redirects shows its 3xx status.

## Writing a plugin

A plugin is a folder:

```
my-plugin/
  plugin.yaml
  plugin.py
```

```yaml
# plugin.yaml
id: my-plugin                 # lowercase letters, digits, dashes
name: My plugin
version: "0.1.0"
floorbit: ">=0.1,<2"          # the Floorbit versions it works with
description: One line about what it does.
uses: [settings, actions, widgets, endpoints, hooks, http, storage]   # only what you need
settings:
  - {key: url, label: URL, type: url}
  - {key: token, label: API token, type: secret}
  - {key: mode, type: select, options: [fast, safe], default: safe}
actions:
  - {id: sync, label: Sync now, permission: plugins.run, dashboard: true,  # any permission; default settings.manage
     params: [{key: dry_run, type: bool, default: true}]}
  - {id: wipe, role: admin, danger: true}                           # asks before it runs
widgets:
  - {id: summary, label: Summary, size: wide, refresh: 60}          # default floorplan.view
endpoints:
  - {id: data, label: Raw data, permission: seats.view}
hooks:
  - {events: [change], action: sync}                                # change, switch.status, health.status, security.finding, power.alert
```

```python
# plugin.py
from floorbit.plugins.base import Plugin as Base, PluginError

class Plugin(Base):
    def run_sync(self, params):
        api = self.ctx.http(self.settings['url'], headers={'Authorization': f"Bearer {self.settings['token']}"})
        items = api.get('/items').json()
        self.ctx.set_state('count', len(items))
        return {'message': f'{len(items)} items'}

    def run_wipe(self, params):
        raise PluginError('Not allowed today')        # shown to the person as is

    def widget_summary(self):
        return {'type': 'stat', 'value': self.ctx.state.get('count', 0), 'unit': 'items'}

    def endpoint_data(self, args):
        return {'count': self.ctx.state.get('count', 0)}

    def test(self):                                     # optional: the Test button
        return 'Connected'
```

### Areas (`uses:`)

| Area | Lets the plugin |
| --- | --- |
| `settings` | have settings (types: string, text, url, secret, bool, int, select, list) |
| `actions` | add actions, run with `POST /api/plugins/<id>/actions/<action>` |
| `widgets` | add dashboard tiles |
| `endpoints` | serve JSON at `GET /api/plugins/<id>/endpoints/<endpoint>` |
| `hooks` | run an action on `change` (any audited change: area, action, target, fields, user) `switch.status` (a switch went offline or came back) `health.status` (a service on the health wall changed colour: id, name, kind, status, previous, summary) `security.finding` (a new security finding: id, kind, severity, switch, port, seat) or `power.alert` (a circuit turned red or tripped: id, name, board, phase, state, pct, seats, switches) |
| `context_menu` | add entries to the floor plan's [right-click menu](context-menu.md) that run one of its actions on a seat or switch: `context_menu: [{action: lookup, targets: [seat], label: "Look up ticket"}]`. The action gets the seat number as its `seat` parameter, or the switch name as `switch`, so it must declare that parameter. An entry shows only to accounts that may run the action; `danger: true` on the action asks first |
| `http` | make outgoing requests with `self.ctx.http(...)` |
| `storage` | keep up to 64 KB of state with `self.ctx.set_state(key, value)` |
| `inventory` | send devices into the [inventory](inventory.md): define `inventory()` returning `[{"id": ..., "name": ..., "role", "model", "serial", "mgmt_ip", "hall", "status"}]`. Floorbit checks each entry, merges them, and never lets a sync overwrite a hand edit or delete a device. Optional: `cables()` returns `[{"switch", "port", "panel", "panel_port", "seat", "label", "color", "length_m", "note"}]` for the [cables page](cables.md) |
| `mapping` | feed the [seat mapping](seat-mapping.md): define `seat_mapping()` returning `{"A-1": {"ip": ..., "mac": ..., "nick": ...}}`. Hand entries always win; bad entries are dropped |
| `monitoring` | be the live data source (one at a time): define `configured()`, `devices()`, `device_details(hostname)`, `resolve_ip(ip, device=None)`, `port_stats(hostname, port)` and `arp(ip_or_mac)`; optionally `device_ports(hostname)` (every port, for the needs-attention list). See the built-in LibreNMS plugin |
| `ports` | act on switch ports (one plugin at a time): define `port_login()`, `bounce_port(target)` and `set_port(target)` (`target["enabled"]` says shut or on). Optional: `send_commands(target)` runs `target["commands"]` and answers `{"output", "refused"}`, and `command_platform()` names the switch software, for [switch commands](commands.md); `open_shell(target)` returns an object with `recv()` (`""` while quiet, `None` once closed), `send(text)`, `resize(cols, rows)` and `close()`, for the [terminal](terminal.md). See [ports.md](ports.md) and the built-in SSH port actions plugin |
| `security` | report [security findings](security.md): define `security_findings()` returning `[{"id", "kind", "severity", "title", "switch", "port", "mac", "ip", "evidence"}]` |
| `power` | send [load readings](power.md) from smart PDUs and meters: define `power_readings()` returning `[{"meter": "db1-1", "amps": 12.4}]` (or `"watts"`) |
| `dns` | send lookups from the event's resolver for [DNS analytics](dns.md): define `dns_queries(since)` returning `[{"ts", "domain", "client", "blocked"}]` after that unix time. Floorbit keeps only hall-wide counts |
| `wifi` | access points for the [Wi-Fi view](wifi.md): define `wifi_aps()` returning `[{"name", "model", "status": "up"/"down", "clients", "radios": [{"band": "2.4"/"5"/"6", "channel", "width", "utilization", "clients"}]}]`. Counts only: anything else is dropped. The built-in UniFi plugin has it |
| `logs` | keep the [syslog](syslog.md) longer and search it: define `push_logs(lines)`, called every 10 seconds with the new lines, and `query_logs(query, start, end, limit)` returning lines newest first in the Logs page's shape (`id` is the time in microseconds) |
| `health` | put services on the [health wall](health.md): define `health_checks()` returning `[{"id", "name", "kind", "status", "summary", "metrics", "link"}]`. See the built-in HTTP check plugin |

Three manifest keys are only for plugins that ship with Floorbit: `default_enabled: true` (on until
an admin turns it off), `enable_env: <VARIABLE>` (on while that variable is `1`) and `core_settings: <section>` (read a settings section that existed before
the plugin, so old env variables keep working).

The loader refuses a plugin whose manifest uses an area it doesn't list, and code whose methods
don't match the manifest (a `run_x` with no action `x`, or an action with no `run_x`). A broken
plugin shows its error on Settings > Plugins and can't be turned on; it never stops Floorbit.

### What Floorbit does for you

- **Permissions:** actions and widgets need the permission they name (`permission:`, see
  [docs/auth.md](auth.md); the older `role: viewer|editor|admin` maps to `floorplan.view`,
  `plugins.run` or `settings.manage`); endpoints need a signed-in account with theirs. None of them
  is ever public, even with `AUTH_PUBLIC_READ` on.
  Changes posted from another site are refused, like every other change.
- **Audit:** every action run is logged with the plugin, the action, the account and the parameter
  *names*. Parameter checks happen before your code runs.
- **Settings from the environment:** each setting can also come from
  `FLOORBIT_PLUGIN_<ID>_<KEY>` (for example `FLOORBIT_PLUGIN_MY_PLUGIN_TOKEN`). A plugin can't pick
  another variable name, so it can't read `SECRET_KEY` or another integration's token that way.
- **Errors:** raise `PluginError("...")` for a message the person should see. Anything else is
  logged on Settings > Plugins > Log, and the person sees that the plugin failed.
- **HTTP:** `self.ctx.http()` sets a timeout (at most 60 s), verifies TLS unless the plugin's
  `verify_ssl` setting is off, and doesn't follow redirects.
- **Hooks** run in the background, so a slow plugin never slows a request.

### Widgets

Widgets are data; Floorbit draws them and never treats their text as HTML. Links must be paths on
this site.

| Type | Fields |
| --- | --- |
| `stat` | `value`, `unit`, `tone` (`ok`, `warn`, `err` or empty) |
| `status` | `items`: `label`, `state` (`up`, `down`, `warn`, `unknown`), `detail` |
| `list` | `items`: `label`, `value`, `tone` |
| `table` | `columns`: `key`, `label`; `rows` |
| `sparkline` | `points`, `value`, `unit`, `min`, `max` |

Every widget can also have `sub` (a line under it) and `link`.

### Developing

```sh
FLOORBIT_DEV_PLUGINS=~/src/floorbit-plugins flask --app app run
```

Each folder in there with a `plugin.yaml` loads as a development plugin. `tests/test_plugins.py`
shows how to test one with Floorbit's test client.
