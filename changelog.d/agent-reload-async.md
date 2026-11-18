### Fixed

- Saving inventory groups, types, telemetry devices or plugin settings no longer waits up to 5 seconds
  for every connected local agent in turn: the agents are told in the background, all at once.
