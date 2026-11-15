### Added

- Hosted Floorbit, part 25: a WebSocket link for the local agent (agent protocol 2, `/api/agent/v2/link`). Calls reach the agent the moment they are made, over one open, encrypted connection. Agents that can't open it keep using the HTTPS long poll. See docs/agent.md, "The WebSocket link".
