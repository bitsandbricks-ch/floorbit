### Changed

- With a database (`FLOORBIT_DATABASE_URL`), the audit log, event timeline, check-in history and event recording are kept in it instead of `.jsonl` files, so several pods share them and nothing is lost when a container is replaced. Each log is imported from its file once. See `docs/database.md`.
