### Added

- `/hall`, a public attendee view: the hall plan with every seat online or offline and how many are
  online, without an account, in English or German. Seat numbers only, no nicks, addresses or switches.
  Off by default; switch it on under Settings > Attendee pages (`ATTENDEE_VIEW`). The same data as JSON
  at `GET /api/public/seats`. See `docs/kiosk.md`.
