### Added

- Seat walk-through (`/seat-walk`): the crew plug a laptop into each seat before the event and press
  Locate; Floorbit finds the seat's switch port from the laptop's address, reading the switch's MAC
  table over SSH when a login is stored, else from telemetry or LibreNMS. A loader while it looks,
  then the port or why it failed, and on to the next seat.
- Seat ports found by the walk-through or by check-ins are cleared one day after the event ends
  (the schedule's end, else when the event was closed).
