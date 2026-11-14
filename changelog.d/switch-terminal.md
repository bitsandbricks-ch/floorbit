### Added

- Switch terminal: a terminal on one switch in the browser (`/terminal`), with the tech's own
  switch login, which is never stored. It needs the new `terminal.open` permission (leads and
  admins). Every line typed goes to the audit log, and lines typed at a password prompt are logged
  as hidden. Terminals close after 10 minutes without typing or 60 minutes in all. See
  `docs/terminal.md`.
