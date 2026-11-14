### Added

- More than one hall or floor, each with its own floor plan, background image, switches and seat
  blocks. A hall picker in the editor's top bar, and a Halls dialog to add, rename and delete halls.
  `/kiosk?hall=` and `/screen?hall=` show another hall; the seat finder names the hall, and the
  attendee view has a tab per hall. See `docs/halls.md`.
- A background image (PNG, JPEG, WebP or SVG) under each hall's plan.
- Seat blocks from a CSV file (`name,x,y,cols,rows`, more columns optional), all or nothing.
- Backups carry every hall with its background image.
