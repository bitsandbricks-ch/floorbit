### Added

- `/report`: a post-event report to read or download as PDF: most seats online and checked in per
  hour, peak bandwidth and bandwidth per hour, data moved, switch outages, the top problem ports and
  the incidents. Nicks and IPs only when an admin asks, and that download is audited. "Start a new
  event" begins the report again. See `docs/report.md`.
- The stats store now also keeps one row per hour for 21 days, switch outages and how often each port
  had a problem, for the report.
