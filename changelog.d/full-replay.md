### Added

- Whole-event replay: the port watch records a frame every five minutes for the whole event,
  thinned out as it gets older (`recording.jsonl`, starts over with a new event). The replay page
  plays it on the plan, with a heatmap of the seat blocks over time (seats online, traffic,
  incidents), a JSON download and a WebM video recorded in the browser. See `docs/replay.md`.
