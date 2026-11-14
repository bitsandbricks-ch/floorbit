### Added

- Problems page (`/problems`, **Problems** in the top bar with a count): offline switches, the
  monitoring source down, red and amber services, security findings and power circuits close to
  tripping, in one list. See `docs/alerts.md`.
- Mute a switch's alerts for 30 minutes to a day while someone works on it (`incidents.work`,
  audited). Muted switches send no Discord messages and are marked on the Problems page.
- Quiet hours (`ALERT_QUIET_HOURS`): Discord messages go out silently and without the mention.
- More switch changes in one poll than `ALERT_GROUP_AFTER` (3) become one Discord message grouped by
  power circuit.

### Changed

- Top bar links show only their icon below 1600 px wide, so the counts stay on screen.
