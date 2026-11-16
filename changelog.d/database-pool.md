### Fixed

- With Postgres, Floorbit no longer keeps one database connection per thread. It shares a pool of
  at most 5 (`FLOORBIT_DATABASE_POOL`), so it can't use up a shared Postgres's connection slots.
