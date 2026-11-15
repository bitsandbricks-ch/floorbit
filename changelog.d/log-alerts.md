### Added

- Log alerts: syslog lines about err-disable, port security, DHCP snooping, MAC flapping, loops,
  storm control and spanning tree changes become needs-attention items on the Problems page, one
  item per pattern, device and port however many lines come (`LOG_ALERT_MINUTES`). Seats and
  switches with recent warnings are underlined on the floor plan, and there's a `logs.alert`
  webhook. See `docs/syslog.md#log-alerts`.
