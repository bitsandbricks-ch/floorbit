### Added

- Syslog from the hall is now a plugin: turn on **Syslog from the hall** under Settings > Plugins
  and set the UDP port, and every local agent listens for syslog without a change to its own
  settings. `FLOORBIT_AGENT_SYSLOG_PORT` on the agent still works.
- Local agents now run the plugins that are on in the hosted Floorbit (LibreNMS, NetBox, Pi-hole,
  health checks, ...) with the settings saved there; the agent keeps them in memory only, and its
  own environment still wins.
