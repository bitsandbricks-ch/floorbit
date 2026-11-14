### Added

- Cables and patching: `/cables` records which switch port goes to which patch panel port and
  seat, and prints labels for both ends with a QR code that opens the cable. Cables in NetBox come
  in with an import (the seat from a `Seat: A-12` description) and stay NetBox's. Changes need
  `floorplan.edit`. See `docs/cables.md`.
