### Changed

- Inventory: a device's status is picked from a list (Active, Planned, Staged, Offline, Failed,
  Decommissioning, In storage) and shown in the reader's language, in the table and the device panel.

### Removed

- Code left behind by the earlier cuts: the old LibreNMS ARP fetch and its cache, the attendee
  hall sketch, and a few helpers nothing called any more.

### Fixed

- Logs page: searching Loki (or VictoriaLogs) again could keep lines from the previous answer on
  screen when several lines had arrived in the same instant.
- German: errors inside an answer that otherwise worked (the syslog's status line, a logs plugin's
  query error) now show in German too.
- Logs page: the syslog receiver's warning no longer shows on the Loki, VictoriaLogs, Floorbit and
  audit log tabs.
- Names, hosts, ports and ids with a newline at the end are refused everywhere they are checked,
  not only in the plugin checks (#769).
- Phones: the Electrics page's circuit buttons and the seat mapping list no longer push the page
  sideways.
