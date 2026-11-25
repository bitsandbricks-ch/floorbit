### Fixed

- The primary of a group of local agents is now one that runs every plugin. An agent with
  telemetry turned off could hold the lease, and then nobody polled the group's devices.
