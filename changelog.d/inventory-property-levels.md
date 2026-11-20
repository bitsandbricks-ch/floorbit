### Added

- A device's properties come in three levels: `system.*` (its own fields, each with who set it and
  what each source last read for it), `auto.*` (what discovery found beyond the fields, such as the
  PoE budget, the VLAN count and sysDescr), and the custom ones people set. The API has them as
  `property_view` on a device; custom names can't start with `system.` or `auto.`.
