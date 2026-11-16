### Fixed

- The floor plan no longer shows up before the sidebar. The server now draws the sidebar's markup
  into the page, ahead of the plan, so it is there in the first paint; the script takes it over
  when it loads. The first paint uses the browser's language and keeps a folded sidebar folded.
