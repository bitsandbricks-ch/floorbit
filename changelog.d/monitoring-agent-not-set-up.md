### Fixed

- With an agent connected but no LibreNMS set up on it, Floorbit no longer asks it for the device list every minute ("LibreNMS failed (MissingSchema)" on the Agents page). It asks the agent whether its monitoring is set up, every 30 seconds.
- A switch that went down or came back shows its new status at once on the plan and its panel, not up to five minutes later.
