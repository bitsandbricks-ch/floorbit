### Changed

- Telegraf reads the core's ARP MAC addresses as plain hex instead of the deprecated `hwaddr` conversion, so the agent's log no longer fills with deprecation warnings on every start.
