### Added

- Inventory for every kind of device: servers, virtual machines and PDUs next to switches,
  routers, firewalls and access points, with specs (platform, OS, CPU, cores, memory, disk, the
  host a VM runs on), their own icon and colour.
- An icon library: admins upload SVG icons (cleaned of anything but shapes) and pick them, in any
  colour, for devices, groups and tags.
- Game servers can say which server or VM they run on; the device page lists what runs on it.
- Interfaces per device, added by hand (ranges like `Gi1/0/1-48`), from NetBox (devices and VMs,
  with addresses) or from the monitoring source's ports. Hand changes are locked against syncs.
- Inventory groups (nested) and tags with icons, colours, properties, feature switches and
  credentials that devices inherit; the device page shows each value and where it comes from.
- Credentials (SSH, SNMP v2c/v3, API token, HTTP login) on a device, tag, group or for all devices,
  encrypted and write-only. Agent plugins get the devices they're switched on for with their
  credential (`/api/agent/v1/inventory/<plugin>`).
- A device whose stored login is refused is blocked for it until a tech clears it, so a wrong
  password doesn't lock the switch account.

- Inventory types: racks and locations, transceivers, VLANs and IP ranges, items and your own
  types, next to devices. Cables, circuits, power boards and patch panels show up there too. Every
  type can have its own fields (text, number, choice, yes/no, links) with defaults.
- NetBox also fills racks, locations, VLANs, prefixes, optics, power panels and power feeds, and
  its custom fields fill the type fields with the same key.

### Changed

- An internet line can be on any device in the inventory, such as the core switch or each firewall.
- Port actions, switch commands, the terminal and config backups can be switched off per device,
  tag or group, and use the inventory's SSH credentials before the stored switch logins.
