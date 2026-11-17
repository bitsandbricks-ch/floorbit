### Added

- For hosted Floorbit: `FLOORBIT_TENANT=<name>` runs a process for one tenant, with its documents
  under `tenants/<name>/` and its Redis keys prefixed, so several tenants can share one database and
  one Redis. Self-hosted installs don't set it and change nothing. See `docs/tenancy.md`.
