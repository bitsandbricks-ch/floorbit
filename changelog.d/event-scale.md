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
- At 2,000 switches and 20,000 seats, one local agent now relays about 1,800 syslog lines a second
  alongside NetFlow, DNS and telemetry: raw flows are compressed lightly, telemetry history is
  trimmed every ten seconds instead of on every point, and syslog reads its settings once per batch.

### Fixed

- With two local agents, a seat lookup no longer waits for one that was just stopped, and the
  Local agents page shows a stopped agent as gone at once, also when it was busy and sent its
  last syslog on the way out.
- While the local agent or LibreNMS is away, seat lookups say "try again shortly" instead of
  "could not resolve", and check-in tries again as soon as it is back.
- With two local agents polling the same switches, port traffic no longer jumps between zero and
  many times the real rate.
- A syslog storm on every port of a big hall no longer grows the Problems list without end: past
  5,000 items, new ones are counted per switch, then per pattern.
- With two local agents for the same halls, a seat lookup asks one of them, and the other only when
  the first doesn't know or doesn't answer within 3 seconds, so LibreNMS isn't asked twice.
