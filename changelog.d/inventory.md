### Added

- Inventory (`/inventory`): every switch, access point and other device, with role, model, serial,
  management IP, hall and notes. Fill it by hand or from plugins. A field changed by hand is never
  overwritten by a sync (until you unlock it), a sync never deletes a device, and every sync is
  logged. See `docs/inventory.md`.

### Changed

- NetBox is now a built-in plugin that feeds the inventory. It is on by default and keeps the
  existing NetBox settings and `NETBOX_*` variables, and the floor plan works as before. It now
  also brings in each device's role, model, serial, management IP and site. Existing switches and
  positions move into the inventory automatically, and old backups still restore.
