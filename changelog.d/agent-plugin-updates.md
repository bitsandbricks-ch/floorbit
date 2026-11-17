### Added

- Plugin updates reach the local agents without a new agent image. Each release signs its plugins;
  the agents install only bundles signed with the key built into their image and newer than what
  they run, go back to the previous version when a new one fails, and say per agent which version
  runs. The hall chooses automatic updates, approval on the agent, or none
  (`FLOORBIT_AGENT_PLUGIN_UPDATES`). Every rollout is in the audit log. See docs/agent-plugins.md.
- Agent plugins can ask whether their agent is the hall's primary (`ctx.primary()`), so two agents
  sharing VRRP addresses never poll a device or try a login twice.
