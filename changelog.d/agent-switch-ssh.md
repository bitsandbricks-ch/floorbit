### Changed

- With a local agent enrolled, port actions, switch commands, config backups and the switch terminal
  open their SSH connection on the agent, in the hall, instead of from the Floorbit server. Stored
  logins are opened for the one call and sent over the agent's link; host keys stay pinned on the
  Floorbit server. The agent only logs in to private addresses, or `FLOORBIT_AGENT_SWITCH_NETS`.

### Fixed

- A switch terminal whose connection broke while typing now says so instead of failing with an error.
