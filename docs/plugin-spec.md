# What a plugin can ship

This is the contract between Floorbit and a plugin: everything a plugin may bring, where each part
runs, what Floorbit checks, and the limits. [Plugins](plugins.md) and
[Agent plugins](agent-plugins.md) explain how to write each part; this page says what is allowed.
A plugin that stays inside it works on every Floorbit in the version range it names, hosted or
self-hosted. Anything outside it is refused when the plugin loads, never at random later.

Rows marked **Next** are agreed but not built yet. Until they are, the loader refuses them, so a
plugin can't depend on them by accident.

## The rules everything else follows

1. **No code in the browser.** A plugin never ships JavaScript, CSS or HTML. Every screen it adds
   is data that Floorbit draws with its own components, and text is always shown as text. That
   keeps the content security policy, the themes, the German and the phone layout the same for
   every plugin.
2. **It says what it touches.** `uses:` in `plugin.yaml` lists the areas; the loader refuses a
   manifest entry or a method for an area that isn't listed. Settings > Plugins and the
   Marketplace show the list.
3. **Signed or not at all.** Outside a development checkout, a plugin is a bundle signed with a key
   built into the image (official) or one the server's operator trusts (community). Its files are
   checked against the signature at install and again every time it loads.
4. **The event network only through the agent.** Methods that talk to the hall's devices run on the
   [local agent](agent.md), never on the Floorbit server. Only official plugins run on agents, so a
   community plugin can't reach the event network.
5. **Privacy is checked, not trusted.** What the agent part sends is marked aggregate or device,
   and aggregate data holding an IP, a network or a MAC address is refused on the agent and again on
   the server.
6. **Changes are audited and permission-checked by Floorbit,** before the plugin's code runs.

## The files in a bundle

| File | Needed | What |
| --- | --- | --- |
| `plugin.yaml` | yes | The manifest: id, name, version, the Floorbit versions it works with, `uses:`, and everything below. Read before any code runs. |
| `plugin.py` | no | The hosted part: `class Plugin(floorbit.plugins.base.Plugin)`. |
| `agent.py` | no | The part on the local agent: `class AgentPlugin(floorbit.plugins.agent.AgentPlugin)` (`agent.module` names another file). |
| more `*.py` | no | Helpers the two import from their own folder (the LAN cache plugin's `logs.py`). |
| `locales/de-CH.json` | no | German for the plugin's own texts (see [Texts and German](#texts-and-german)). |
| `README.md`, `CHANGELOG.md`, `LICENSE` | no | Shown on the Marketplace page. |
| `SIGNATURE.json` | in a bundle | Written by the release workflow: the hash of every other file, signed. |

Not allowed in a bundle: symlinks, anything but regular files, more than 200 files, more than 8 MB
packed or 32 MB unpacked, compiled or native code (`.so`, wheels), and anything under `static/` or
`templates/` (rule 1).

Python packages: a plugin may import the Python standard library and what Floorbit itself installs
(`requests`, `PyYAML`, `cryptography`, `paramiko`, ...: `requirements.txt`). It can't install more.
If a plugin needs a package, it goes into Floorbit's requirements through a pull request there.

## What it can add

### Settings and secrets

| Can ship | Status | Limits and checks |
| --- | --- | --- |
| Settings of type `string`, `text`, `url`, `secret`, `bool`, `int`, `select`, `list` | Ships | Keys: lowercase, digits, `_`, up to 40. `int` has `min`/`max`; `select` needs `options`. Each gets a fixed env name, `FLOORBIT_PLUGIN_<ID>_<KEY>`; a plugin can't read any other variable. |
| Secrets | Ships | Write-only on the page and in the API (reported as set or not set), never in the audit log, sent to an agent over its link only and kept in its memory. Sealed at rest with the [vault](credentials.md#secret-settings) like switch logins. |
| Device credentials | Ships | A plugin doesn't store logins itself. With `agent.targets.credentials: [ssh, snmp_v2c, snmp_v3, api, http]` it gets the inventory devices it is turned on for, with the credential of a kind it can use, decrypted for that call. |
| Where it is on | Ships | On or off for the whole Floorbit; an agent part can be limited to inventory groups, tags or devices (`agent.targets`). |

### Actions, hooks and endpoints

| Can ship | Status | Limits and checks |
| --- | --- | --- |
| Actions (`run_<id>(params)`) | Ships | Each names a [permission](auth.md) (default `settings.manage`) and may be `danger: true` (asks first). Floorbit checks the permission, the parameters and the CSRF token, and writes the audit log, before the code runs. |
| Hooks on `change`, `switch.status`, `health.status`, `security.finding`, `power.alert` | Ships | Run one of the plugin's actions in the background, on a few shared threads with a bounded queue, in the tenant and event the change happened in (see [Limits](#limits)). |
| Endpoints (`endpoint_<id>(args)`) | Ships | Read-only JSON at `/api/plugins/<id>/endpoints/<endpoint>`, for an account with the permission it names. Never public, even with `AUTH_PUBLIC_READ`. |
| Right-click entries on the floor plan | Ships | `context_menu:` runs one of its actions on a seat or a switch; shown only to accounts that may run it. |
| A Test button (`test()`) | Ships | Runs on the agent for a plugin that reaches the event network. |
| Its own HTTP routes, pages served from Python | Never | Only the endpoints above. |

### Screens

All of these are data. Floorbit draws them in its own style, with the accent colours set for the event, in light
and dark, on phones and big screens.

| Can ship | Status | Limits and checks |
| --- | --- | --- |
| Dashboard tiles (`widgets:`): `stat`, `status`, `list`, `table`, `sparkline` | Ships | `small` or `wide`, refreshed every 10 s or slower. Up to 50 rows, 12 columns, 500 points; links only to paths on this site. Usable on [dashboards](dashboards.md) and kiosk walls. |
| Its page under Settings > Plugins | Ships | Floorbit builds it: what it may touch, settings, Test, actions, log, the agents that run it. |
| An icon (`icon:`) | Ships | A name from Floorbit's icon set (the sidebar's and the inventory's icons), shown in the plugin list and the Marketplace. A name Floorbit doesn't know is refused at load. No SVG or image files: a plugin never ships something the browser draws as is. |
| Side panel boxes (`panels:` for a `seat`, `switch` or `device`) | Ships | A widget in the side panel when that thing is open: the plan's seat and switch panels, the inventory's device panel. `panel_<id>(target)` gets `{kind, id}` and returns a widget, within the same time budget as a tile. Each entry names its permission; unknown keys in an entry are refused. |
| Floor plan layers (`layers:`) | **Next** | `layer_<id>()` returns `{seat or switch: {value, tone, label}}` plus a legend; drawn like the heatmap, one layer at a time, under the plan's own filters. |
| Pages in the sidebar (`pages:`) | **Next** | A page made of the plugin's own widgets, in the sidebar's *Plugins* group, for accounts with the permission it names. |

### Data Floorbit uses

Each area is an interface: Floorbit calls named methods and checks every answer, dropping what
doesn't fit. Hand edits in Floorbit always win over what a plugin sends.

| `uses:` | The plugin answers | Runs |
| --- | --- | --- |
| `inventory` | devices (and optionally cables) for the [inventory](inventory.md) | agent, when it reads the network |
| `mapping` | seat to IP, MAC and nick for the [seat mapping](seat-mapping.md) | agent |
| `monitoring` | live switch status, ports, traffic, ARP and MAC tables (one source at a time) | agent |
| `ports` | bounce, shut or turn on a port; switch commands; the terminal (one at a time) | agent |
| `health` | services on the [health wall](health.md) | agent |
| `security` | [security findings](security.md) | agent |
| `power` | circuit load from PDUs and meters ([power](power.md)) | agent |
| `dns` | resolver lookups, kept only as hall-wide counts ([DNS](dns.md)) | agent |
| `wifi` | access points and radio counts, no client names or MACs ([Wi-Fi](wifi.md)) | agent |
| `logs` | keep the syslog longer and search it ([syslog](syslog.md)) | server |
| `brackets` | tournament brackets ([tournament](tournament.md)) | server |

The method names and shapes are in [Plugins](plugins.md#areas-uses).

### The part on the agent

| Can ship | Status | Limits and checks |
| --- | --- | --- |
| Collectors: `ctx.send(kind, payload)` for each kind under `agent.sends` | Ships | Each kind is `aggregate` or `device`; `latest: true` keeps only the newest. 4 MB per payload as JSON; spooled on the agent's disk while the uplink is down (256 MB and 24 h per plugin). |
| Listeners: `listen_udp`, `listen_http` (TLS when the hall set a certificate) | Ships | Closed when the plugin stops. |
| Read-only calls (`agent.calls`) | Ships | `ctx.agent_call(...)` from the hosted part; 15 s. |
| Actions in the hall (`agent.actions`) | Ships | Reached only from one of the plugin's own actions (permission and audit), and only when the hall's `FLOORBIT_AGENT_ALLOW_ACTIONS` allows it; 120 s. |
| Questions to the hosted part (`agent.fetches`) | Ships | `ctx.fetch(kind)` answered by `agent_get_<kind>(agent)`. |
| Logins to devices | Ships | Asks `ctx.may_login(...)` first and reports `ctx.auth_failed(...)`; a refused credential is never tried again until a tech clears it. With two agents in a hall, only `ctx.primary()` polls. |
| Self-health and metrics | Ships | `ctx.health(status, message)`, `ctx.error(...)`, `ctx.counter(...)`, `ctx.gauge(...)`: on the Local agents page, in the agent's `/metrics` as `floorbit_agent_plugin_<name>{plugin="<id>"}` and in `python -m floorbit_agent check`. The last 10 errors and 40 numbers per plugin are reported. |
| A folder of its own (`ctx.state_dir`) | Ships | In the agent's state volume. |
| Updates without a new agent image | Ships | Official bundles only, never a downgrade, needs `agent_api` the image has; rolled back on its own when it fails in its first five minutes. |

### Storage

| Can ship | Status | Limits and checks |
| --- | --- | --- |
| Small state: `ctx.set_state(key, value)` | Ships | JSON, 64 KB per plugin, per tenant. Kept when the plugin is updated, rolled back or removed. |
| Documents: its own JSON collections | **Next** | Per tenant, under the plugin's id, 256 KB per document and 5 MB per plugin, in whichever store Floorbit uses (files, SQLite, Postgres). |
| Migrations | **Next** | `schema: <n>` in the manifest and `migrate(from_n, store)` on the hosted part, run once per tenant before the new version takes over; a failed migration keeps the old version running. |
| Its own database tables or SQL | Never | Floorbit runs on files, SQLite and Postgres, with tenants; plugin SQL would tie it to one of them and around the tenant scoping. |

### Texts and German

| Can ship | Status | Limits and checks |
| --- | --- | --- |
| English texts in the manifest and in what it returns | Ships | Names, labels, help, widget texts, messages from `PluginError`. |
| German | Ships | `locales/de-CH.json` in the plugin's folder: `{"English text": "Swiss German text"}`, with `{}` where a value goes (`"Waved {} times": "{} Mal gewunken"`; `{1}`, `{2}` reorder). Used for its name, description, settings (label, help, placeholder), actions, tiles, right-click entries, messages and errors. A text it doesn't list falls back to Floorbit's own catalog, then to English. Standard German (`de`) is made from it like everywhere else ("ss" to "ß"). Up to 2,000 texts and 256 KB; a file with a different number of `{}` on the two sides is refused. |

### Permissions it asks for

A plugin doesn't add roles or permissions. Each action, endpoint, tile, panel, layer and page names
one of [Floorbit's permissions](auth.md), and Floorbit checks it. What a plugin may touch is the
sum of its `uses:`, the permissions it names, its agent block (what it sends and how private,
the actions it can run in the hall) and the device credentials it can use. Settings > Plugins shows
all of it, and the Marketplace shows the same summary on each card before you install, from the
index. The index build refuses a release whose `plugin.yaml` Floorbit's loader would refuse.

## Limits

| What | Limit |
| --- | --- |
| Plugin id | 2 to 40 characters, lowercase letters, digits and dashes, starting with a letter; `floorbit` is taken |
| Bundle | 8 MB packed, 32 MB unpacked, 200 files, regular files only |
| `plugin.yaml` | 256 KB, refused unread past that |
| Loading `plugin.py` | 15 s; one that doesn't finish loading (or calls `sys.exit()`) shows an error and Floorbit starts without it |
| Marketplace index | 2 MB; read with the cap, so a bigger one is never in memory |
| State | 64 KB per plugin and tenant |
| Outgoing HTTP (`ctx.http`) | needs `http` in `uses:`; timeout 10 s by default, 60 s at most; no redirects; TLS verified unless its own `verify_ssl` setting is off |
| Plugin log | the last 200 lines of up to 500 characters, in memory |
| Widget | 50 rows or items, 12 columns, 500 points, texts cut at 40 to 200 characters |
| Agent payload | 4 MB per send; 256 MB and 24 h of spool per plugin |
| Agent call / action | 15 s / 120 s |
| Hooks | at most 4 running at once per Floorbit and 200 waiting; past that the oldest are dropped and the plugin's log says so |
| Tiles and endpoints | an answer within 10 s, or the request gets an error and the plugin's log says so; at most 4 of one plugin's at once, past that "still busy" at once |

## What Floorbit guarantees in return

- A broken plugin never stops Floorbit: a bad manifest, an import error, an import that never
  finishes, a method that raises or even calls `sys.exit()` is shown on its page and in its log,
  and the rest keeps running.
- An update that doesn't load leaves the previous version running; *Back to* undoes an update.
- A withdrawn version is never installed, and where it runs the page says so.
- Settings and state survive updates, rollbacks and removal.
- Every install, update, rollback, removal, on/off, action and refused send is in the audit log
  or the plugin's log.

## Checklist for a new plugin

1. Start from [floorbit-plugin-template](https://github.com/bitsandbricks-ch/floorbit-plugin-template).
2. List only the `uses:` you need, and name the narrowest permission for each action and tile.
3. Anything that talks to the hall's network goes in `agent.py`. Mark every `sends:` kind
   honestly; aggregate means hall-wide numbers with no addresses.
4. Raise `PluginError` with a sentence for the person; let anything else go to the log.
5. Test against the Floorbit commit in `FLOORBIT_REF`, with the fakes in `tests/`: no real devices.
