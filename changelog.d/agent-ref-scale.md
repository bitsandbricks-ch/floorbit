### Changed

- Built and tested with the local agent that does 16 seat lookups at once, reads NetFlow in its own
  thread and sends a syslog batch the hosted side finds too big again in halves.
