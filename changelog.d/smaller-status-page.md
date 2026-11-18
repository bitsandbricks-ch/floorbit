### Removed

- The public attendee view (`/hall`, with a dot per seat) is gone; `/hall` now leads to the network
  status page. The status page drops planned maintenance, the Atom feed (`/status.atom`) and the
  option to name switches (`STATUS_SWITCH_NAMES`). It keeps the state, the affected halls, blocks
  and rows, and the crew's updates. `ATTENDEE_VIEW` is ignored now.
