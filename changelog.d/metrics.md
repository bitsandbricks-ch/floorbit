### Added

- Prometheus metrics: `GET /api/metrics` counts seats by state, seats with problems, check-ins,
  incidents, switches and needs-attention items per hall, plus the age of the last port read. Off
  by default; scrape it with a read-only API token. No seats, nicks or addresses. See
  `docs/metrics.md`.
