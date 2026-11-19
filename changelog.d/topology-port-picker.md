### Added

- Topology: the link form offers the switch's ports as the monitoring source reads them, free ones
  first with their state and speed, and the ones a link already uses with where it goes. Typing a
  port still works when a switch can't be read. New: `GET /api/links/ports?switch=` (`floorplan.edit`).

### Changed

- Topology: saving the diagram's places answers a fixed error text when it fails.
