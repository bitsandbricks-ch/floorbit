### Fixed

- On Postgres, a statement the database refused (for example a name with a NUL byte from a switch)
  no longer counts as the database being down. Before, it turned saving off for everyone for the
  next seconds, and again on every such statement. Device and port names with a NUL byte are cleaned
  before they are stored, and a telemetry series whose name the table can't hold is left out on its own
  instead of stopping the whole sample.
