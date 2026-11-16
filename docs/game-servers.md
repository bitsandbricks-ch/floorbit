# Game servers

**Network › Game servers** (`/game-servers`) shows the hall's game servers: whether each one is up, how
many players are on it, which map it runs and how fast it answers, with the players over the last
half hour. The crew sends RCON commands from the same page. The servers also show as tiles on the
[service health wall](health.md), so a server that stops answering pages the crew like DHCP or DNS would.

## Adding a server

Admins (`settings.manage`) press **Add game server** and give:

| Field | What |
| --- | --- |
| Name | What the crew calls it, for example `CS Hall A`. |
| Game | Optional, shown under the name. |
| Host, query port | Where Floorbit asks it, for example `192.0.2.50` and `27015`. |
| Ask with | **Steam server query (A2S)** for Counter-Strike, Team Fortress, Rust, ARK, Valheim and most other Steam games; **Minecraft status** for Minecraft (Java); **Only check the port** for anything else. |
| RCON port, RCON password | Optional. Without them the server is watched, but has no console. |

Floorbit asks every server each `GAME_INTERVAL` seconds (default 30, at least 10). The query is the
one a server browser sends: it changes nothing on the server.

With a [local agent](agent.md) enrolled, the agent asks from the event network instead, and the page
says so. That is how a hosted Floorbit reaches servers on the LAN.
Without an agent the server's own queries follow `PROBE_NETS` (see [services](services.md#what-the-server-itself-may-reach)).

## RCON

**RCON console** opens a console for one server. It needs `games.rcon`, which techs, leads and admins
have. Type a command, press Enter and the server's answer shows underneath.

- **Commands that stop the server, change the map or throw players out** (`quit`, `stop`, `restart`,
  `changelevel`, `map`, `kick`, `ban`, `exec`, `mp_restartgame` and the like) are sent only after you
  confirm them.
- **Every command is in the [audit log](audit.md)** (area *games*) with who sent it and to which server.
  A command that sets a password (`sv_password`, `rcon_password`) is logged by its name only.
- One command per send, up to 500 characters; the answer is cut at 64 KB.

## The RCON password

The password is kept like the [switch logins](credentials.md): encrypted with AES-256-GCM under the key
in `FLOORBIT_SECRET_KEY_FILE`, never sent back to the browser, and opened only for the one command.
When editing a server, leave the field empty to keep the password, or switch on **Remove the RCON
password**. `python -m floorbit.vault rotate` moves the RCON passwords to a new key along with the
switch logins.

## API

- `GET /api/game-servers`: `{"servers": [...], "interval", "last_poll", "via_agent", "counts", "players"}`.
  Each server has `id`, `name`, `game`, `host`, `port`, `query`, `rcon_port`, `rcon` (whether a password
  is set), `status` (`up`, `down`, `unknown`), `info` (`name`, `map`, `game`, `version`, `players`,
  `max_players`, `bots`, `ping_ms`), `error`, `checked_at`, `since` and `history` (`[time, players]`).
- `POST /api/game-servers`, `PUT /api/game-servers/<id>`, `DELETE /api/game-servers/<id>` (`settings.manage`):
  `{"name", "game", "host", "port", "query", "rcon_port", "rcon_password", "clear_rcon"}`.
- `POST /api/game-servers/check/<id>` (`games.rcon`): ask one server now.
- `POST /api/game-servers/rcon/<id>` (`games.rcon`): `{"command", "confirm"}` → `{"server", "command", "answer"}`.
  A command that needs confirming answers 409 with `"confirm": true`.
