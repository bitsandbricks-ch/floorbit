### Added

- **Front door for attendees** plugin: the local agent's front door (check-in finds the seat PC's
  port, the seat speed test measures the hall) is set up under Settings > Plugins like syslog and
  flows from the hall.

### Changed

- Everything a local agent does for the event is set up in Floorbit (Settings > Plugins); the
  agent's own environment no longer sets plugins (`LIBRENMS_URL`, `NETBOX_URL`,
  `FLOORBIT_PLUGIN_*`, `FLOORBIT_AGENT_PLUGINS`, `FLOORBIT_AGENT_SYSLOG_PORT`, `_FLOWS_PORT`,
  `_CAPTIVE`, `_FRONT_DOOR`). An agent that still has them sends them once after its update, and
  Floorbit takes them over for each plugin not set up there yet, with an audit log entry.
- Self-hosted with the agent next to Floorbit, syslog, flows and the front door are turned on once
  on the ports the compose file and the Kubernetes pod publish, instead of by variables on the agent.
- The check-in note on phones (plugin) also answers the crew's seat walk-through.
