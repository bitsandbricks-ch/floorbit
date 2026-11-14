### Added

- **Stats** page (`/stats`): bandwidth now, the peak in the last hour, 24 hours and of the event,
  traffic over time, uplink load per switch, seats online, ports up, down and with errors, and the
  top talkers. Built from the port reads the needs-attention watch already makes; 24 hours of
  samples and the peak are kept in Redis. `/stats?screen=1` is the big-screen version for kiosk and
  ops screens, with the kiosk theme and no nicks. Admins can reset the event's peak. Uplinks are
  ports whose description says `uplink` or `trunk` or names another switch (`STATS_UPLINK_PATTERN`).
  See `docs/stats.md`.

