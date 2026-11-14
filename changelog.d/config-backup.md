### Added

- Switch configs: back up the running config of up to 20 switches at a time with the tech's own
  login (never stored) and see what changed since the event's baseline, as a diff. Secrets are
  taken out before a copy is kept, and only changes are kept, the last 50 per switch. Needs the new
  `configs.read` permission (leads and admins). See `docs/configs.md`.
