### Added

- VictoriaLogs plugin: turn it on under Settings > Plugins to keep the syslog longer in the
  VictoriaLogs that `docker compose --profile logs` starts, and search it with LogsQL on the Logs page.

### Removed

- `FLOORBIT_VICTORIALOGS_URL`: it never sent anything. Use the VictoriaLogs plugin instead.
