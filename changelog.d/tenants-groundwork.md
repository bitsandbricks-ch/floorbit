### Added

- Groundwork for several events and tenants: Floorbit now knows which documents belong to the
  organisation (accounts, settings, plugins) and which to one event (floor plan, logs, check-ins).
  An existing install is one tenant with one live event, with every file and database row where it
  was; nothing to do on upgrade. See `docs/tenancy.md`.
