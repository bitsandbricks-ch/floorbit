### Added

- Every answer says where its time went (a `Server-Timing` header the browser's network panel
  shows: time inside Floorbit, computing, and with the database), and requests that take longer
  than a second are logged, so a slow page can be traced from a browser export.
