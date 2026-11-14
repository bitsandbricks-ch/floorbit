### Added

- Incident board (`/incidents`): problems at a seat or switch, open → being worked → fixed, with
  teams, assignees and notes. Open incidents show as red rings on the floor plan. Working an
  incident needs `incidents.work` in its team; giving it to someone else or moving it needs
  `incidents.assign`. See `docs/incidents.md`.
- Seat helpdesk: a printable QR code per seat opens a help page where attendees tap what is wrong,
  without an account and without giving anything personal. Links are signed, reports are rate
  limited, repeats count up, and each report arrives with the seat's switch port and link state.
