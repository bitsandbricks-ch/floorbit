### Added

- Public dashboards: a dashboard with **Public** on opens without signing in, for a screen in the hall,
  and then shows only what anyone may see (the plan with public marks, switch and seat counts, the
  switches down, texts). See `docs/dashboards.md`.
- A "Switches down" tile: which switches are down and for how long, longest first.
- Plan panes on a dashboard choose their plan marks: all, only the public ones (Overview and Safety),
  or none.

### Changed

- `/kiosk` opens the ready-made Kiosk dashboard, which is public and now shows the plan with the
  public marks, switches up, seats online and the switches down. `/kiosk?hall=` and `?theme=` carry
  over; `/kiosk?view=heat` opens the floor plan's traffic view. `/screen` shows the Kiosk dashboard
  and the plan's traffic view for its `floor` and `heat` views.

### Removed

- The old kiosk page and its options `title`, `refresh`, `labels`, `grid`, `marks` and `reload`.
