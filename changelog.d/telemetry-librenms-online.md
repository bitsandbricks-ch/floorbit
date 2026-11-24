### Fixed

- While LibreNMS polls the switches, the Telemetry page and its widget no longer show them as down
  between two device fact reads: the agent still asks each device every 30 seconds whether it answers.
