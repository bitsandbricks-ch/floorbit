### Added

- Plugins can keep their own JSON documents (up to 5 MB per plugin and tenant, in whichever database Floorbit uses), and move them to a new shape with `schema:` and `migrate()` when they update. A Marketplace update whose migration fails keeps the version before.
