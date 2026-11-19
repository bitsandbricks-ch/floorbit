### Added

- An agent's own settings (the address in the hall, metrics, buffer, Telegraf port, log level, VRRP) and its plugin settings are set on its page in Floorbit. A value the agent's own environment sets still wins, and the page shows where each value comes from. Its limits (actions, plugin updates, networks) stay in the hall and are shown read-only. See `docs/agent.md`.
- **Roll key** makes a new key that the agent fetches itself; nothing in its environment changes.
- Floorbit signs the agents' HTTPS certificates with its own CA, for the names listed on the agent's page; crew devices install the CA once (**Download CA**).
