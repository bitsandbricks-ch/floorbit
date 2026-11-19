### Added

- Discovery fills each interface's MAC, IPv4 addresses, access VLAN and access or trunk mode from
  SNMP, and adds the VLANs and networks the devices know as VLAN or IP range entries. A device's
  VLANs and networks are in its API (`discovered`), and `GET /api/endpoints?device=` lists what was
  plugged into any of its ports.
