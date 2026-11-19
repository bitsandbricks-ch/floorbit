### Added

- Discovery: inventory devices are filled from what telemetry (SNMP) or LibreNMS polls: model,
  serial, platform and software version, CPU, cores, memory, disk, the new location field and the
  interfaces. It runs every 15 minutes (`DISCOVERY_MINUTES`, 0 turns it off) and with Sync now,
  and only fills in: values set by hand or by NetBox stay.
- SNMP polling reads the memory use of Cisco switches.
