### Changed

- Floorbit keeps its documents in SQLite (`floorbit.db` in the state folder) when
  `FLOORBIT_DATABASE_URL` isn't set, instead of JSON files. An existing install needs nothing:
  on its first start after the update, each JSON file and `.jsonl` log is imported once and then
  left alone as a backup. Editing `data.json` by hand no longer changes anything.
- The IP and MAC history and the lite telemetry series are kept in the database on every install,
  so they survive a restart.
- A save on a full or read-only disk answers the same clear "not saved" message as before.

### Removed

- Keeping documents as JSON files (the old default without `FLOORBIT_DATABASE_URL`).
