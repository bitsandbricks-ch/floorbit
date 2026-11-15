### Added

- Hosted Floorbit, part 24: the agent protocol has a version (`Floorbit-Agent-Protocol`, now 1), so the agent can move to its own repository and be released apart. A Floorbit that doesn't speak the agent's protocol answers 426 and says which one it does, and the agent stops with that message instead of retrying. See `docs/agent.md`.
