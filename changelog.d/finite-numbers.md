### Fixed

- A request with `NaN`, `Infinity` or a number too big for a float (`1e999`) in its JSON body now
  gets a clear 400 instead of a server error. Browsers never send these values, so only scripts and
  API clients notice.
- A switch or patch panel can no longer be placed at "nan" or "inf". Such a position was saved, and
  the floor plan, the switch list and the cable plan then failed to load for everyone.
