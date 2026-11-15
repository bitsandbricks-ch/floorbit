### Added

- Hosted Floorbit, part 17: syslog through the local agent. With `FLOORBIT_AGENT_SYSLOG_PORT` set, the agent takes the event network's syslog and sends it on over HTTPS to the hosted Logs page, keeping up to 20,000 lines while the hosted Floorbit can't be reached. The hosted allow-list still applies to the original senders. See `docs/agent.md`.

### Fixed

- A syslog line with an earlier time than the sender's last one (a relayed backlog, or a sender's own clock) was taken as over the rate cap, and one old line late in the log could hide newer warnings from the floor plan markers.
