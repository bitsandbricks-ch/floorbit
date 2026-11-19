### Added

- A **Telemetry** tab on every inventory device and group: which local agent collects from the
  device, and a port for SNMP, gNMI and the API each, inherited from the group above. A device's
  tab also shows when it was last heard, **Test now** and **Raw data**.
- A device given to an agent is collected by that agent alone, and calls about it go there; while
  that agent is away the others take it over.

### Fixed

- A device's telemetry port no longer applies to SNMP, gNMI and the API at once.
