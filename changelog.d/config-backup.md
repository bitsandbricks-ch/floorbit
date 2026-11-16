### Added

- Switch configs: back up the running config of up to 20 switches at a time and see what changed
  since the event's baseline, as a diff. Every night at 04:00 (`CONFIG_BACKUP_HOUR`) Floorbit also
  backs up each switch a stored switch login covers. Secrets are taken out before a copy is kept,
  and only changes are kept, the last 50 per switch. Copies go in the database when there is one.
  Needs the new `configs.read` permission (leads and admins). See `docs/configs.md`.
