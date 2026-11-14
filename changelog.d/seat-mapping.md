### Added

- Seat mapping (`/seat-mapping`, editors and admins): set a seat's IP, MAC, nick and a note by
  hand, see which source gave each field, and import or export the hand entries as CSV. Hand
  entries win over every other seat source; empty fields are filled from plugins, check-ins and
  `seats.json`. See `docs/seat-mapping.md`.
- Plugins can feed the seat mapping with `uses: [mapping]` and a `seat_mapping()` method.
