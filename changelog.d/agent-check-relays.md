### Changed

- Hosted Floorbit, part 19: the local agent's `check` also tries syslog and flows when their ports are set, and a stopping agent (`docker stop`, Ctrl+C) sends the syslog lines still waiting before it goes. See `docs/agent.md`.
