### Changed

- Ready for a 1,000-switch, 10,000-seat hall with syslog, NetFlow, DNS and device telemetry all
  coming in: seat lookups ask LibreNMS about a third as often and run about ten times faster
  (cached on the agent, one lookup per address at a time, the switch list remembered), a page
  request no longer re-reads all settings, accounts and plugins, and the local agent's return
  after an outage is noticed at once instead of up to a minute later.
- A big hall's minute of telemetry is sent in parts under the size limit; telemetry history in
  memory is kept compact and bounded, and written to a database in batches.
- Syslog keeps up on SQLite and Postgres: log sizes are counted as lines arrive, the timeline is
  written in batches, and settings and document times are checked once a second.
