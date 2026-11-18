### Fixed

- Telemetry history without VictoriaMetrics (the lite mode in the database) saves a sample about ten
  times faster. At a bigger event, saving one sample used to take longer than the 30 seconds between
  samples, so the history fell behind and held a server thread the whole time.
