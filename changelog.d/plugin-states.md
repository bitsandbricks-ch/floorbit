### Changed

- Settings > Plugins: each card says what the plugin does (Receiving, Waiting, Not configured, No agent, Failing, Off) and has the same layout, with its switch at the bottom right. The LAN cache shows up there when its data arrives without the plugin installed (#1435).
- Syslog and flows through the local agent listen on the agent's fixed ports (udp/5514 and udp/2055, published as 514 and 2055) as soon as their plugin is on; the port moved under Advanced (#1436).
