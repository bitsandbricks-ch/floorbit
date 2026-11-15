### Added

- Event changelog: `/timeline` puts every change during the LAN on one timeline: audit log edits
  and sign-ins, switch outages, incidents opened and fixed, alerts (security, power, service
  health, forecast, log alerts, monitoring) and each start or update of Floorbit. It can be filtered
  by kind, text and time, and exported as CSV or JSON. Alerts and starts go to a new
  `timeline.jsonl` journal. It needs `audit.read`. See `docs/timeline.md`.
