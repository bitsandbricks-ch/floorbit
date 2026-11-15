### Added

- Hosted Floorbit, part 22: `python -m floorbit.agent health` says whether the hosted Floorbit answered the agent in the last two minutes, and `docker-compose.agent.yml` uses it as the container's health check, so `docker ps` shows a lost uplink. See `docs/agent.md`.
