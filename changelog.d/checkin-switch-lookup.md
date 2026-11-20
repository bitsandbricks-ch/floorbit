### Added

- When the ARP and MAC tables don't know a checked-in PC yet, Floorbit asks the switches for that one PC with a few SNMP requests, in network segments with lookups on. It asks the switches of the seat's row first, then its block, then the rest of the VLAN. Lookups run from doors open for 6 hours and while check-ins keep coming; the crew can open them by hand on the Check-in page, which also shows a to-do when a check-in can't be looked up.

### Changed

- The seat walk asks the monitoring source first, then the switches over SNMP, and uses SSH last.
