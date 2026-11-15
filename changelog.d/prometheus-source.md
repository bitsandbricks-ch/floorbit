### Added

- Prometheus plugin: switch status and port state, traffic and errors from the SNMP exporter's
  `if_mib` series, as the monitoring source instead of LibreNMS. See `docs/plugins.md`.

### Changed

- The monitoring source is the first plugin that is on and set up, so turning on another source
  works while LibreNMS has no URL.
