### Added

- Floorbit can keep its documents (floor plan, accounts, settings, templates, past events, plugin
  state, check-ins) in SQLite or Postgres: set `FLOORBIT_DATABASE_URL`. Existing files are imported
  on the first start, once. `/healthz` answers 503 when the database doesn't. See `docs/database.md`.
