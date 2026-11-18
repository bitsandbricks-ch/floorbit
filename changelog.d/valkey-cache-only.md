### Changed

- The stats (bandwidth, peak, the replay's seat changes and the event report's hours), the last
  good monitoring answers and the latest traffic summary from the agent are kept in the database
  instead of Valkey (Redis). They survive a restart of Valkey and are the same on every worker and
  pod; Valkey now holds only the LibreNMS cache and the live updates between pods. Stats kept in
  Valkey before the update start again from the update.

### Removed

- The standalone flow collector (`python -m floorbit.flows`): flows come in through the local
  agent, as they already had to.
