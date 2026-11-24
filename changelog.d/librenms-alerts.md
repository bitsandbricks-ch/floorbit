### Added

- LibreNMS alerts through the local agent: LibreNMS's API transport posts each alert to the agent
  (port 9530), and it shows on the Problems page at once and wakes the status monitor. A recovery
  clears it. Settings > Plugins > LibreNMS alerts shows the URL, token and body to paste.
