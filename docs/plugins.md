# Plugins

Plugins add things to Floorbit without changing its core: buttons that run code (actions), tiles on
the dashboard (widgets), read-only JSON (endpoints) and code that runs when something changes
(hooks). The design is borrowed from labdex (manifest, `Plugin` class, widgets as data) and Hubra
(`uses:`: a plugin can touch only the areas it lists). [What a plugin can ship](plugin-spec.md) is
the contract: every part a plugin may bring, where it runs, and the limits.

## Turning plugins on

Settings > Plugins lists every plugin with its version and whether it is on. Plugins start
**off**, except the few that ship with Floorbit and replace what used to be built in (NetBox); those
start on and do nothing until they're configured. Turning one on or off is in the audit log. Each
plugin has its own page, `/settings/plugins/<id>`, with what it may touch, its test, actions, log
and settings. Secrets are write-only there, as everywhere. The Settings search finds plugin settings
too and links to the plugin's page.

The tiles of the plugins that are on show in the [widget gallery](dashboards.md#the-widget-gallery)
(`/widgets`), for anyone signed in whose role is allowed to see them, and go on any dashboard as a
**Tile** pane.

Where plugins come from:

| Trust | Where | Notes |
| --- | --- | --- |
| Ships with Floorbit | `floorbit/builtin_plugins/` | Reviewed with Floorbit itself. |
| Official | the [Marketplace](marketplace.md), signed with the key built into the image | Reviewed and released from the `floorbit-plugin-*` repositories. |
| Community | a Marketplace source the server's operator added, signed with a key the operator trusts | Runs inside Floorbit like the others: trust its author as you trust Floorbit. |
| Development checkout | the folder in `FLOORBIT_DEV_PLUGINS` | For writing plugins. **Never set it in production**: the code runs inside Floorbit. |

Nothing unsigned is ever installed. See [Marketplace](marketplace.md).

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

## In the Marketplace

These integrations used to be built in and now install from the [Marketplace](marketplace.md).
Each repository's README says what it reads and which settings it takes.

| Plugin | Feeds | Repository |
| --- | --- | --- |
| UniFi | monitoring, Wi-Fi | [floorbit-plugin-unifi](https://github.com/bitsandbricks-ch/floorbit-plugin-unifi) |
| MikroTik | monitoring | [floorbit-plugin-mikrotik](https://github.com/bitsandbricks-ch/floorbit-plugin-mikrotik) |
| Zabbix | monitoring | [floorbit-plugin-zabbix](https://github.com/bitsandbricks-ch/floorbit-plugin-zabbix) |
| Aruba AOS-CX | monitoring | [floorbit-plugin-aruba](https://github.com/bitsandbricks-ch/floorbit-plugin-aruba) |
| AdGuard Home | [DNS analytics](dns.md) | [floorbit-plugin-adguard-home](https://github.com/bitsandbricks-ch/floorbit-plugin-adguard-home) |
| Pi-hole | [DNS analytics](dns.md) | [floorbit-plugin-pihole](https://github.com/bitsandbricks-ch/floorbit-plugin-pihole) |
| LAN cache | [LAN cache](lancache.md) | [floorbit-plugin-lancache](https://github.com/bitsandbricks-ch/floorbit-plugin-lancache) |
| Shelly, Home Assistant | [power](power.md) | [floorbit-plugin-shelly](https://github.com/bitsandbricks-ch/floorbit-plugin-shelly), [floorbit-plugin-home-assistant](https://github.com/bitsandbricks-ch/floorbit-plugin-home-assistant) |

## Built in: Grafana Loki

Keeps the [syslog](syslog.md) longer than Floorbit's own 24 hours. Set Loki's URL (for example
`http://loki.example.com:3100`), and the tenant, username and password when your Loki needs them
(the tenant is sent as `X-Scope-OrgID`). Every 10 seconds Floorbit pushes the new lines to
`/loki/api/v1/push` with a few labels (`job="floorbit"`, `source="syslog"`, `device`, `severity`, and
`event` when the **Event label** is set); the rest of a line is JSON, so `| json` gets `program`,
`message`, `port` and `seat`. Lines Loki didn't take are sent again next time. The Logs page then
gets a **Grafana Loki** source to search it with LogQL, over up to 30 days.

## Built in: VictoriaLogs

Keeps the [syslog](syslog.md) longer than Floorbit's own 24 hours, in the VictoriaLogs that
`docker compose --profile logs up -d` starts (URL `http://victorialogs:9428`) or your own. Set the
tenant as `AccountID:ProjectID` when it keeps several, and a username and password when it sits
behind basic auth. Every 10 seconds Floorbit sends the new lines to `/insert/jsonline`: the message
is `_msg`, the streams are `job` and `device`, and `severity`, `program`, `port`, `seat`, `source`
and `event` (when the **Event label** is set) are fields. Lines it didn't take are sent again next
time. The Logs page then gets a **VictoriaLogs** source to search it with LogsQL, over up to 30 days.

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

    def test(self):                                     # optional: the Test button (on the agent for LAN plugins)
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
| `panels` | add a box to the side panel of a seat or a switch on the floor plan, or of a device in the inventory: `panels: [{id: load, for: seat, label: "Seat load"}]` (`for:` is `seat`, `switch` or `device`; not `on:`, which YAML reads as true). `panel_<id>(target)` gets `{"kind": "seat", "id": "A-12"}` and returns a [widget](#widgets). Optional: `permission:` (floorplan.view by default) and `refresh:` in seconds (a whole number, 10 to 86,400, 60 by default). Each box loads on its own, so a slow or broken plugin shows only its own error |
| `http` | make outgoing requests with `self.ctx.http(...)` |
| `storage` | keep up to 64 KB of state with `self.ctx.set_state(key, value)` |
| `documents` | keep its own JSON documents: `self.ctx.docs('notes').put('a', {...})`, up to 5 MB; with `schema:` and `migrate(from_schema, store)` when their shape changes ([plugin-spec.md](plugin-spec.md#storage)) |
| `layers` | a layer on the floor plan: `layer_<id>()` gives seats a tone (`ok`, `warn`, `err`, `info`) and a legend; picked under Layers on the plan ([plugin-spec.md](plugin-spec.md#screens)) |
| `pages` | pages of its own in the sidebar's Plugins group, laid out from its widgets and actions (`pages:`); see [plugin-spec.md](plugin-spec.md#screens) |
| `inventory` | send devices into the [inventory](inventory.md): define `inventory()` returning `[{"id": ..., "name": ..., "role", "model", "serial", "mgmt_ip", "hall", "status"}]`. Floorbit checks each entry, merges them, and never lets a sync overwrite a hand edit or delete a device. Optional: `cables()` returns `[{"switch", "port", "panel", "panel_port", "seat", "label", "color", "length_m", "note"}]` for the [cables page](cables.md), and `configured()` says whether its settings are filled in: one that isn't set up yet isn't synced and isn't listed as a source |
| `mapping` | feed the [seat mapping](seat-mapping.md): define `seat_mapping()` returning `{"A-1": {"ip": ..., "mac": ..., "nick": ...}}`. Hand entries always win; bad entries are dropped |
| `monitoring` | be the live data source (one at a time): define `configured()`, `devices()`, `device_details(hostname)`, `resolve_ip(ip, device=None)`, `port_stats(hostname, port)` and `arp(ip_or_mac)`; optionally `device_ports(hostname)` (every port, for the needs-attention list) `port_clients(hostname)` (the MAC table as `[{port, mac, vlan}]`, for the clients the patch plan does not explain) and `neighbours(hostname)` (LLDP or CDP as `[{port, remote, remote_port, protocol}]`, for the [topology](topology.md)) and `device_facts(hostname)` (what the device is, shaped like telemetry's: `vlans`, `networks`, `transceivers`, `poe`, `routes`, for [discovery](inventory.md#discovery)). See the built-in LibreNMS plugin |
| `ports` | act on switch ports (one plugin at a time): define `port_login()`, `bounce_port(target)` and `set_port(target)` (`target["enabled"]` says shut or on). Optional: `send_commands(target)` runs `target["commands"]` and answers `{"output", "refused"}`, and `command_platform()` names the switch software, for [switch commands](commands.md); `open_shell(target)` returns an object with `recv()` (`""` while quiet, `None` once closed), `send(text)`, `resize(cols, rows)` and `close()`, for the [terminal](terminal.md). See [ports.md](ports.md) and the built-in SSH port actions plugin |
| `security` | report [security findings](security.md): define `security_findings()` returning `[{"id", "kind", "severity", "title", "switch", "port", "mac", "ip", "evidence"}]` |
| `power` | send [load readings](power.md) from smart PDUs and meters: define `power_readings()` returning `[{"meter": "db1-1", "amps": 12.4}]` (or `"watts"`) |
| `dns` | send lookups from the event's resolver for [DNS analytics](dns.md): define `dns_queries(since)` returning `[{"ts", "domain", "client", "blocked"}]` after that unix time. Floorbit keeps only hall-wide counts |
| `wifi` | access points for the [Wi-Fi view](wifi.md): define `wifi_aps()` returning `[{"name", "model", "status": "up"/"down", "clients", "radios": [{"band": "2.4"/"5"/"6", "channel", "width", "utilization", "clients"}]}]`. Counts only: anything else is dropped. The built-in UniFi plugin has it |
| `logs` | keep the [syslog](syslog.md) longer and search it: define `push_logs(lines)`, called every 10 seconds with the new lines, and `query_logs(query, start, end, limit)` returning lines newest first in the Logs page's shape (`id` is the time in microseconds) |
| `health` | put services on the [health wall](health.md): define `health_checks()` returning `[{"id", "name", "kind", "status", "summary", "metrics", "link", "capacity"}]` (`capacity` optional, for the "full in" forecast). See the built-in HTTP check plugin |

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
  logged on Settings > Plugins > Log, and the person sees that the plugin failed. When one of your
  methods has failed on every call for a few minutes, Problems says the plugin keeps failing, with
  the last message. Each method counts on its own: your seat mapping working doesn't hide your Wi-Fi
  access points failing.
- **HTTP:** `self.ctx.http()` sets a timeout (at most 60 s), verifies TLS unless the plugin's
  `verify_ssl` setting is off, and doesn't follow redirects.
- **Hooks** run in the background, so a slow plugin never slows a request.

### Widgets

Widgets are data; Floorbit draws them and never treats their text as HTML. Links must be paths on
this site.

| Type | Fields |
| --- | --- |
| `stat` | `value`, `unit`, `tone` (`ok`, `warn`, `err` or empty); optional `min`, `max` (shows as a gauge) |
| `status` | `items`: `label`, `state` (`up`, `down`, `warn`, `unknown`), `detail` |
| `list` | `items`: `label`, `value`, `tone`; optional `number` and `max` (shows as bars or a pie) |
| `table` | `columns`: `key`, `label`; `rows` |
| `sparkline` | `points`, `value`, `unit`, `min`, `max` |
| `series` | `series`: up to 4 of `label`, `points` (`[unix seconds, value]`, oldest first) and optional `ghost: true` (a comparison line, drawn dotted, such as yesterday at the same times); `unit`; optional `marks`: up to 50 of `t` (unix seconds), `label` and `tone` (`ok`, `warn`, `err` or empty), drawn as lines across the graph |

Every widget can also have `sub` (a line under it) and `link`. On a dashboard, a widget is drawn
small, medium or large to fit its box ([Dashboards](dashboards.md#tiles-that-fit-their-box)): send
all your rows, Floorbit shows what fits.

The same widgets fill the boxes a plugin adds to side panels (`panels:`).

### Developing

```sh
FLOORBIT_DEV_PLUGINS=~/src/floorbit-plugins flask --app app run
```

Each folder in there with a `plugin.yaml` loads as a development plugin. `tests/test_plugins.py`
shows how to test one with Floorbit's test client.
