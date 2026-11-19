### Added

- The agent's log says more about telemetry: when Telegraf starts, stops or reloads, each Test now and its result, and every minute how many points each device gave and which devices gave nothing, with their problem. With the agent's `FLOORBIT_AGENT_LOG_LEVEL=debug`, also Telegraf's own lines, each post and each API poll round.
