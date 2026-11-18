### Fixed

- A local agent whose clock is off (a box without NTP) no longer silences log alerts or loses its
  syslog lines: Floorbit puts the agent's times right with the clock the agent sends along, and
  says once in its log that the agent's clock is off. Needs the agent update that sends its clock.
