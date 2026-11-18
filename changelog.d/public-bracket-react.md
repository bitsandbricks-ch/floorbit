### Changed

- The public tournament brackets (`/bracket`, `?screen=1` for a big screen, `?id=` for one bracket)
  are part of the React app now, with the event's logo and a language picker on phones. With this,
  every public page refreshes through the React app; `static/js/refresh.js` and `status.js` are gone.
  `/bracket.json` is unchanged.
