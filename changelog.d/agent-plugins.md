### Added

- Agent plugins: a plugin can now run a part of itself on the local agent, in the hall (an
  `agent:` block in `plugin.yaml` and an `agent.py`). The hosted Floorbit tells each agent which
  plugins to run and with which settings; the agent part sends its results back, answers
  read-only calls, and runs actions only when the hall allows them on the agent
  (`FLOORBIT_AGENT_ALLOW_ACTIONS`). What a plugin marks as aggregate is refused when it holds an IP
  or MAC address. Each plugin's health, numbers and recent errors show up in the agent's report.
  See docs/agent-plugins.md.
