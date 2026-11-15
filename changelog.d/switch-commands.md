### Added

- Switch commands: a new page (`/commands`) runs saved commands such as port status, the MAC
  address table or port errors on up to 20 switches at once and shows the answers side by side.
  Show commands are for techs; commands that change something (clearing counters) need the new
  `commands.change` permission (leads and admins) and a second confirm. Admins add their own
  commands. The tech's switch login is used for the run and never stored, and every run is in the
  audit log, per switch and without its output. See `docs/commands.md`.
