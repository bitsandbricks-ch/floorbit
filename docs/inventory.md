# Inventory

The inventory is every switch, router, firewall, server, virtual machine, access point, PDU and
other device Floorbit knows about, with their interfaces. Floorbit owns
the list: it works with no plugin at all, filled by hand on the **Inventory** page (`/inventory`)
or by placing switches on the floor plan. Plugins such as NetBox add to it.

Every device, group and tag has its own page, with no side panel in between: a device opens at
`/inventory/devices/<id>` with tabs for its overview, interfaces, telemetry, settings and
credentials; a group at `/inventory/groups/<id>`, a tag at `/inventory/tags/<id>` and the
defaults for all devices at `/inventory/defaults`, each with tabs for its details, telemetry,
settings (properties and feature switches) and credentials. Other entries (cables, transceivers, ...) open at
`/inventory/entries/<type>/<id>`. The links can be shared and bookmarked.

## What each device has

Name, role (switch, router, firewall, access point, server, virtual machine, PDU, other), model,
serial, management IP, hall or site, location (where the device says it is), status and notes,
plus where it sits on the floor plan. Every
device on the floor plan is an inventory device; unplaced ones wait in the floor plan's "add
switch" dialog.

Servers, VMs and firewalls also have **specs**: platform, operating system, CPU, cores, memory
(MB), disk (GB) and, for a VM, the device it runs on (**host**, picked from the inventory). Plugins
feed them like any other field.

Each device can have its own **icon** and **colour** (or take them from its group or a tag),
**tags**, a **group**, **properties** (name and value pairs, such as `rack` or `snmp.port`),
**feature switches** and **credentials**; see [Groups and tags](#groups-and-tags).

The device page lists what **runs here**: VMs whose host it is, and [game servers](game-servers.md)
that run on it or on one of those VMs. If the device goes down, those go down with it.

### Icon library

Next to the built-in icons, admins upload their own under **Inventory > Icons** (SVG, at most
64 KB). Floorbit rebuilds each file from plain shapes: scripts, event handlers, links, external
references, embedded images, `foreignObject` and styles are dropped, a file with a DOCTYPE is
refused, and every colour becomes `currentColor`, so the icon takes the colour picked for the
device, group or tag. The page draws an uploaded icon as an image mask, never as inline markup.
Uploaded icons are served at `/api/icons/<id>.svg` for anything else that shows icons. Icons on
the floor plan can use them too: the editor's icon list has them under **Uploaded**, and the plan,
the kiosk and the attendee hall view draw them in the icon's colour. Removing an icon puts the
devices, groups and tags that showed it back on their default icon, and turns plan icons that used
it into the info icon.

## Interfaces

A device's interfaces are its ports: switch ports, a server's NICs, a firewall's interfaces, a VM's
virtual NICs. Each has a type (copper, fiber, DAC, virtual, LAG, wireless, management), speed,
MAC, addresses, untagged VLAN, mode (access, trunk, routed), description, whether it is enabled
or a management port, and the LAG it belongs to.

- **By hand:** open a device's page, the **Interfaces** tab, **Add**. A range adds many at
  once: `Gi1/0/1-48`, `Te1/1/1-4, mgmt0`.
- **From NetBox:** the NetBox plugin sends each device's interfaces (`/api/dcim/interfaces/`, with
  their addresses from IPAM) and the virtual machines with theirs, on every inventory sync.
- **From the monitoring source:** **Take ports from monitoring** copies the ports LibreNMS (or
  device telemetry) knows for every switch, router, firewall, access point, server and PDU.

They follow the device rules, per interface: a field changed by hand is locked against syncs, a
sync never deletes (an interface a plugin stops sending is marked gone), and removing a fed
interface hides it.

## Groups and tags

**Groups** sort devices (Hall A > Row 1 > Access switches); they nest up to 8 deep and a device is
in one group at most. **Tags** are labels (core, lab, rented); a device or a group can have
several. Both carry:

- an icon and a colour,
- properties,
- feature switches,
- credentials,
- and, for groups, tags.

A device inherits from its tags, its group, the group's tags, the parent group and so on, up to
**All devices** (the defaults). The most specific one wins:

    the device > its own tags > its group > that group's tags > the parent group > ... > All devices

The device page shows every inherited value and where it comes from.

### Properties in three levels

A device's page (`GET /api/inventory/<id>`, `property_view`) shows its properties in three levels:

| Level | What | Each value has |
| --- | --- | --- |
| `system.*` | The device's own fields: `system.name`, `system.model`, `system.serial`, `system.mgmt_ip`, `system.os`, `system.location`, `system.group`, `system.tags`, ... | `value` (what every view uses), `set_by` (`hand`, `discovery` or the feeding plugin, such as `netbox`) and `sources`: what each source last read for it (`{"telemetry": "FOC0000X0AA", "netbox": "..."}`) |
| `auto.*` | What discovery found that has no field of its own: `auto.vlans.count`, `auto.networks.count`, `auto.optics.count`, `auto.routes.count`, `auto.routes.default_gateway`, `auto.poe.budget_w`, `auto.poe.used_w`, `auto.interfaces.count`, `auto.snmp.sysdescr` | `value`, `source`, `seen` |
| no prefix | The properties people set, inherited from tags, groups and the device type | `value`, `from` (where it is set) |

A hand value still wins over discovery (see Discovery below), and the source that disagrees stays
visible next to it. Custom property names can't start with `system.` or `auto.`.

### Feature switches

Per device, tag, group or for all devices, Floorbit's own per-device features can be switched off
(port actions, switch commands, the terminal, config backups; on unless switched off), and plugins
switched on. A plugin with a part on the [local agent](agent.md) works on a device only
where it is switched on **and** a credential for it resolves.

### Credentials

SSH logins, SNMP v2c communities, SNMP v3 users, API tokens and HTTP logins can be stored on a
device, a tag, a group or All devices: the nearest one wins, so a group's login is overridden by
the device's own. They are kept like [stored switch logins](credentials.md): encrypted at rest,
write-only (the API says which are set and by whom, never the secret), opened only at the moment
of use, and every use is in the audit log. The older **Settings > Switch logins** (by name pattern)
moved in here once: see [credentials.md](credentials.md).

Only admins set and remove credentials; editors see which are set.

### Blocked after a failed login

When a stored credential is refused (a port action, a command, the terminal, a config backup, or
an agent plugin), the device is **blocked** for that credential: nothing tries it again, so a wrong
password doesn't lock the account on the switch. The device shows the block with what failed and
when; any tech (`ports.act`) presses **Clear** once it is fixed. Setting the credential again
clears its blocks too. A typed login still works while a stored one is blocked.

## For agents

Agent plugins get the devices they work on with their settings (`settings["targets"]`, see
agent plugins in [agent.md](agent.md)). Agent parts that ask themselves use, with the agent's key:

| Request | What it does |
| --- | --- |
| `GET /api/agent/v1/inventory/<plugin>?kinds=ssh,snmp_v3` | The devices the plugin is switched on for that have a usable credential of those kinds: `{"devices": [{"id", "name", "address", "role", "platform", "model", "properties", "credential": {"id", "rev", "kind", "username", "secret", ...}}], "etag"}`. `If-None-Match`: 304 while nothing changed |
| `POST /api/agent/v1/inventory/auth-failed` | `{"device_id", "credential_id", "rev", "plugin", "message"}`: block the device for that credential |

Handing out logins is in the audit log each time the set changes.

## Types and entries

Devices are one **type** of inventory entry. The others sit in tabs on the Inventory page:

| Type | Where its entries live |
| --- | --- |
| Cable, Circuit, Power board, Patch panel | The cables, power and floor plan pages, as before. The inventory shows them and adds fields, tags, a group and properties; name and route stay on their own page. |
| Rack or location | The inventory (height in U, hall). |
| Transceiver | The inventory (device, port, form factor, media, speed, serial). |
| VLAN or IP range | The inventory (VLAN ID, prefix, gateway, purpose). |
| Item | The inventory, for anything else worth listing. |

Admins add their own types under **Inventory > Types**, and give any type, built-in or their own,
extra **fields**: text, number, choice, yes/no, or a link to a device or an entry of another type (the rack a
switch sits in, the VLAN of a range).
Each field can have a default. Entries also take an icon, colour, tags, a group and properties,
and inherit them like devices do: entry > its tags > group > parent groups > the type > all
entries. Credentials and feature switches stay with devices. A custom type with entries can't be
deleted until they are.

## How plugins feed it

A plugin with `uses: [inventory]` returns its devices when asked (**Sync now** on the Inventory
page, or the sync button on the floor plan). Floorbit merges them with these rules:

- **Hand edits win.** When you change a field a plugin also sends, the field is locked: syncs
  leave it alone. The Inventory page shows a lock and what the plugin says; **Use NetBox's value**
  unlocks it and takes the plugin's value again.
- **A sync never deletes.** A device a plugin stops sending is marked "Gone from NetBox" and stays.
- **Deleting a fed device hides it**, so the next sync doesn't bring it back. Turn on *Show hidden*
  to see it and show it again. Devices made by hand are really deleted.
- **First sync joins by name.** If a plugin sends a device whose name matches one made by hand,
  the two become one device. Fields that differed stay as you set them (locked).
- Every device remembers which plugins feed it and the last values each one sent.
- Every sync is logged: added, updated, joined, gone, and how many hand-edited fields it kept.
  The Inventory page shows the last sync per plugin; `GET /api/inventory/log` has the history.

Bad entries from a plugin (no ID, no name, an IP that isn't one) are skipped and counted, never
stored.

### Syncing on its own

Set **Inventory sync (minutes)** under Settings > General (`INVENTORY_SYNC_MINUTES`) and Floorbit
runs the same sync by itself, so a switch added in NetBox during setup shows up without anyone
pressing **Sync now**. 0 (the default) is off; less than 5 counts as 5, at most once a day. The
time counts from the newest sync, by hand or not, and a failed one waits the same time before the
next try. With several pods only the leader syncs. The Inventory page says how often it runs.

### Discovery

Floorbit also fills the devices from what the monitoring source polls, like a discovery: model,
serial, platform and software version, CPU, cores, memory, disk, location and the interfaces. With
[telemetry](telemetry.md) the agent asks each device by SNMP every five minutes (sysDescr,
sysLocation, ENTITY-MIB for the chassis model and serial, HOST-RESOURCES-MIB for memory, disks and
CPUs, the Cisco memory pool); with LibreNMS it takes what LibreNMS knows of the device.

- It is a set of **actions**, each for the kinds of device it fits and on its own clock:

  | Action | Devices | Every |
  | --- | --- | --- |
  | `identity`: model, serial, software, location, memory, disks, CPU | all | 60 minutes |
  | `interfaces` | switches, routers, firewalls, access points, servers, PDUs | Discovery (minutes) |
  | `networks`: VLANs and networks | switches, routers, firewalls, servers, VMs | Discovery (minutes) |
  | `optics`: transceivers | switches, routers, firewalls | 60 minutes |
  | `poe`: the PoE budget | switches | Discovery (minutes) |
  | `routes` | firewalls | Discovery (minutes) |

  **Discovery (minutes)** is under Settings > General (`DISCOVERY_MINUTES`, 15 by default; less
  than 5 counts as 5, 0 turns every action off). An admin sets one action's own interval with
  `PUT /api/inventory/discovery/actions/<id>` (`{"minutes": 30}`, 0 for off, `null` for the
  default). `GET /api/inventory/discovery` lists the actions with their last run (when, how many
  devices, how many changed). **Sync now** runs them all; `POST /api/inventory/discovery/run`
  runs some (`{"actions": ["optics"]}`) or all, on every device or one (`{"device": "<id>"}`), and
  a run for one device doesn't move the schedule. The Inventory page shows the last run next to
  the plugins'.
- It only fills in. A field gets the discovered value when it is empty, or when it still holds
  what discovery put there last, so a software upgrade shows up. A value typed by hand or sent by
  another plugin (NetBox) stays; the run counts it as kept. Empty a field and the next run fills
  it again.
- It matches inventory devices by name (the short name too) or management IP, and never adds or
  deletes a device or changes its name, role, address or status.
- Interfaces come in as with **Take from monitoring** on the device's Interfaces tab, for
  switches, routers, firewalls, access points, servers and PDUs that are up. With telemetry they
  bring their MAC, IPv4 addresses, access VLAN and whether they are access or trunk ports (Cisco:
  vmVlan and the trunk status; others: the Q-BRIDGE port VLAN).
- The VLANs each device knows (with their names) and the networks on its interfaces become
  **VLAN or IP range** entries, with the same rules as a plugin's: what you change stays, nothing
  is deleted. A device's own list is `discovered` in `GET /api/inventory/<id>`; what was plugged
  into its ports is `GET /api/endpoints?device=<name>` ([IP and MAC history](endpoints.md)).
- The optics ENTITY-MIB lists (module or port rows with a serial and a model like `SFP-10G-SR`,
  `GLC-LH-SMD` or `QSFP-40G-SR4`) become **Transceiver** entries, one per serial, with the device,
  the port it sits in (ENTITY-MIB's alias mapping, its parent's, or the same name), and form
  factor, media and speed read from the model. An optic moved to another port or switch follows.
  A device's own list is `discovered.transceivers`.
- A switch's PoE budget and what it gives now are `discovered.poe` (`budget_w`, `used_w`); the
  per-port PoE is live data on its ports ([telemetry](telemetry.md)).
- A firewall's routes are `discovered.routes` (`network`, `next_hop`, `interface`, `proto`), the
  default route first.
- A device that didn't answer keeps what it said last, so its optics and VLANs aren't marked gone
  while it is away.
- The platform it finds (Cisco IOS, IOS-XE, NX-OS, Linux, ...) also sets what telemetry does
  automatically for the device, such as MAC tables per VLAN on Catalyst IOS.

**Drift.** What discovery keeps instead of overwriting, it lists as drift: per device, each field
where the inventory and the device disagree (the serial typed by hand against the one it reports;
memory and disk only when more than 10% apart), a different hostname (sysName), a different
management address (not when the device has a `telemetry_address`), and interfaces: in the
inventory but not on the device, on the device but hidden here, or with a locked value the device
reports differently. Each row says what is configured, what is actual and since when.
`GET /api/inventory/<id>` has the device's `drift`, `GET /api/inventory` a count per device, and
`GET /api/inventory/drift` all of it.

### What NetBox sends besides devices

The NetBox plugin also fills these types, with the same rules (hand edits lock a field, nothing is
deleted, the first sync joins by name):

- **Racks and locations** from racks and locations.
- **VLANs and IP ranges** from VLANs and prefixes.
- **Transceivers** from modules and from inventory items that look like optics (SFP, QSFP, ...).
- **Power boards and circuits** from power panels and power feeds. They go onto the power page;
  a board that already exists there by name is joined, never overwritten.
- **Custom fields** fill the type's field with the same key.

NetBox versions or tokens without one of these lists just skip it. A sync through the local agent
brings devices only for now.

## Who may do what

Viewers and up see the inventory and the icon library; admins upload, rename and remove icons. Editors and up add, change, hide and sync devices, interfaces,
groups and tags. Admins set credentials and manage types; techs and up clear blocked logins. Changes are in the
audit log (area *inventory*, *credentials* and *icons*), with field names, never values or secrets.

## API

| Request | What it does |
| --- | --- |
| `GET /api/inventory` | Devices (`?hidden=1` with hidden ones), the plugins that feed it and their last sync |
| `POST /api/inventory` | Add a device (`name` required) |
| `PATCH /api/inventory/<id>` | Change fields; `unlock: ["model"]` takes the plugin's value again; `hidden: false` shows it again |
| `DELETE /api/inventory/<id>` | Delete (made by hand) or hide (fed by a plugin) |
| `POST /api/inventory/sync` | Run every inventory plugin that's on |
| `GET /api/inventory/log` | The last 50 syncs (editors and up) |
| `GET /api/inventory/<id>` | One device with its interfaces, what it inherits and from where, its blocks, and its properties in three levels (`property_view`) |
| `POST /api/inventory/<id>/interfaces` | Add interfaces: `{"names": "Gi1/0/1-48", "type": "copper"}` |
| `PATCH` / `DELETE /api/inventory/<id>/interfaces/<iid>` | Change (`unlock: [...]` as for devices) or remove one |
| `POST /api/inventory/interfaces/sync` | Take the ports from the monitoring source |
| `GET /api/inventory/groups` | Groups, tags, the defaults, and the features and icons there are |
| `POST /api/inventory/groups`, `PATCH` / `DELETE /api/inventory/groups/<id>` | Groups (`name`, `parent_id`, `icon`, `color`, `tags`, `properties`, `features`) |
| `POST /api/inventory/tags`, `PATCH` / `DELETE /api/inventory/tags/<id>` | Tags |
| `PATCH /api/inventory/defaults` | Properties and features for all devices |
| `GET` / `PUT /api/inventory/credentials`, `DELETE /api/inventory/credentials/<id>` | Credentials: `{"owner_type": "device" \| "tag" \| "group" \| "defaults", "owner_id", "kind", "username", "secret", "priv_secret"}` |
| `GET /api/inventory/blocks`, `POST /api/inventory/blocks/clear` | Blocked logins; clear with `{"device_id", "credential_id"?}` |
| `GET /api/icons`, `GET /api/icons/<id>.svg` | The icon library and one cleaned icon |
| `POST /api/icons`, `PATCH` / `DELETE /api/icons/<id>` | Upload `{"name", "svg"}`, rename `{"name"}`, remove. Admins |
| `GET /api/inventory/types` | Every type with its fields and how many entries it has |
| `POST /api/inventory/types`, `PATCH` / `DELETE /api/inventory/types/<id>` | Add a type, change its fields, icon, colour and properties, delete an empty custom type. Admins |
| `GET /api/inventory/entries?type=<id>` | Entries of one type (or all but devices) |
| `POST /api/inventory/entries/<type>` | Add an entry (`name`, `fields`, `tags`, `group_id`, `properties`, `icon`, `color`) |
| `GET` / `PATCH` / `DELETE /api/inventory/entries/<type>/<id>` | One entry with what it inherits; change it; delete it |

The floor plan's `/api/switches` API works on the same list.

## Upgrading

The first time Floorbit reads `data.json` after the upgrade, it moves hand-placed switches and the
cached NetBox devices with their positions into the inventory, keeping their IDs. Backups made
before the upgrade still restore and are moved over the same way. Nothing to do by hand.
