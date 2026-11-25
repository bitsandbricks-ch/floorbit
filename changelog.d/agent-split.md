### Added

- Two or more local agents for the same devices split them: each device has one owner agent that
  alone polls it and logs in to it, and only that agent's devices move when it goes. Traps,
  streams and syslog go to every agent; the owner handles them and the others keep the last minute for a
  takeover (#1441).
