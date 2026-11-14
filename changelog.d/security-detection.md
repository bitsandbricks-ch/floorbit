### Added

- Security page (`/security`): rogue DHCP servers, ARP spoofing, MAC flapping, loops and broadcast
  storms from security plugins (new plugin area `security`), each pointing at a switch port and a
  seat. Findings show as dashed rings on the floor plan, new high and medium ones go to Discord
  (where, never MACs or IPs), and the page needs `seats.view`. See `docs/security.md`.
- One-click **Shut port** for a finding, through the port actions (`POST /api/ports/shutdown` with
  the finding). Ports Floorbit shut are listed until someone turns them on again
  (`POST /api/ports/enable`).
- Port action plugins now also define `set_port(target)` (shut or turn on).
