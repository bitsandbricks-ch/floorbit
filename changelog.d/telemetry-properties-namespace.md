### Changed

- A device's telemetry settings are properties under `telemetry.` now: `telemetry.drivers`,
  `telemetry.agent`, `telemetry.address`, `telemetry.verify_tls`, `telemetry.snmp.fdb`,
  `telemetry.snmp.vlans`, `telemetry.snmp.port`, `telemetry.gnmi.port`, `telemetry.api.port`,
  `telemetry.api.url` and `telemetry.mdt.node`. Floorbit moves the old names once when it starts.
