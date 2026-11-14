### Added

- Seats view: the seat inspector can bounce the seat's port (with the tech's own switch login)
  and flag the seat for a tech, like the floor plan editor.

### Fixed

- Bouncing a seat's port now also works for a seat with no IP or MAC in the seat mapping (often
  the offline seats that need it most): Floorbit takes the port from the switch's port
  descriptions.
