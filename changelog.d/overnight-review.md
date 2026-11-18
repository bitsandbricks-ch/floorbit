### Changed

- Inventory: a device's status is picked from a list (Active, Planned, Staged, Offline, Failed,
  Decommissioning, In storage) and shown in the reader's language, in the table and the device panel.

### Removed

- Code left behind by the earlier cuts: the old LibreNMS ARP fetch and its cache, the attendee
  hall sketch, and a few helpers nothing called any more.

### Fixed

- Logs page: searching Loki (or VictoriaLogs) again could keep lines from the previous answer on
  screen when several lines had arrived in the same instant.
