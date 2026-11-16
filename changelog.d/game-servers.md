### Added

- Game servers (Network › Game servers): whether each one is up, its players, map and ping, asked every 30 seconds with the Steam server query (A2S), the Minecraft status or a plain port check, and shown on the service health wall too. With a local agent the agent asks from the event network.
- An RCON console for each game server, for techs and up (new permission `games.rcon`). Commands that stop the server, change the map or throw players out are sent only after confirming, and every command is in the audit log. The RCON password is encrypted like the switch logins, write-only and opened only for the one command.
