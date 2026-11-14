### Added

- Offline mode: when the monitoring source (LibreNMS) stops answering, switch status, port details
  and IP lookups answer from the last good data, greyed out on the floor plan with "Offline since
  14:32, data from 14:31". The last good data is kept in Redis, or in `monitoring-cache.json`
  without Redis. `GET /api/monitoring/health` says whether the source is answering. See
  `docs/offline.md`.

### Changed

- A monitoring outage sends one Discord message ("LibreNMS is unreachable", then "is back") instead
  of switch alerts, and the status monitor starts from a fresh baseline afterwards, so an outage
  never floods the channel.
