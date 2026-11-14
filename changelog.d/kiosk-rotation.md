### Added

- `/screen` rotates big-screen views on a timer (`?views=floor,heat,stats,health&every=30`), with a
  QR code to the seat finder in the corner. Views stay loaded so they keep their live updates.
- `/kiosk?view=heat` colours every seat by its traffic right now, from the stats reads
  (`GET /api/stats/seats`, seat numbers and numbers only).
- `/find`: players type their seat number on their phone, without an account, and see where it is
  in the hall (block, row, seat, and the plan with the seat marked), in English or German. Finding by
  nick is off unless `SEAT_FINDER_NICKS=true`; `SEAT_FINDER=false` switches the page off. See
  `docs/kiosk.md`.
