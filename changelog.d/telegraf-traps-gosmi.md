### Fixed

- SNMP traps (linkDown, linkUp) from switches reach Floorbit through the agent. Telegraf dropped each one with "Error resolving OID", because it tried to name the trap's OIDs with net-snmp tools and MIB files the agent doesn't have. It now uses its built-in MIB reader, and Floorbit reads the numeric OIDs.
