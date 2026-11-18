### Fixed

- Many open pages at once no longer stop Floorbit from answering. Before, 64 open tabs (crew
  screens, or attendees on the status page) took every server thread for their live updates and
  no page loaded any more. Now a quarter always stays free for pages, attendees get at most half
  of the rest, and a page that finds no free slot works without live updates and asks again a
  little later.
