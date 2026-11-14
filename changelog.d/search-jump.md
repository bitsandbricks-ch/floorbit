### Added

- The floor plan search finds players by IP and MAC too (any spelling), and a full IP or MAC is
  looked up on the network: through the ARP table when no seat source knows it, with the switch
  port it is plugged into. Picking a result jumps to the seat and lights up its switch. Needs
  `seats.view`. See `docs/seat-mapping.md`.
