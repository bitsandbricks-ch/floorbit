### Added

- Discovery takes VLANs, networks and transceivers from LibreNMS too, and the interfaces' MAC,
  IPv4 addresses, VLAN and access or trunk mode, and the VLAN interfaces that become proposed lookup
  segments, so it works with LibreNMS alone. With telemetry
  on as well, telemetry's answer comes first and LibreNMS fills the gaps. Needs a local agent
  that knows `device_facts`.

### Fixed

- Discovery now keeps the VLAN interfaces it finds, so their lookup segments are proposed.
