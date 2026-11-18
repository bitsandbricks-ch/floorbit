### Changed

- The public hall view (`/hall`) and the "find your seat" page (`/find`) are part of the React app
  now, with the event's logo, a language picker and the hall's walls and marks on the map. They read
  the new `GET /api/public/hall` and `GET /api/seat-finder?q=`; the old Jinja templates and
  `static/js/hall.js` are gone.
