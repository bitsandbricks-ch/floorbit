### Changed

- Hosted Floorbit, part 23: the local agent gzips what it sends (answers, syslog batches, traffic summaries) once the hosted Floorbit says it takes that, which saves most of the event's uplink on big inventories and syslog. The protocol table in `docs/agent.md` now lists the syslog and traffic requests too.
