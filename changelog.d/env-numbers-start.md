### Fixed

- A typo in a number setting (`REDIS_PORT`, `REDIS_DB`, `AUTH_SESSION_HOURS`,
  `FLOORBIT_DATABASE_WAIT`, `FLOORBIT_DATABASE_POOL`) no longer stops Floorbit at start with a bare
  traceback: the log names the setting and the default is used. `AUTH_SESSION_HOURS` of 0 or less
  no longer signs everyone out at once; it is raised to six minutes.
