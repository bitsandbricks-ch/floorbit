### Added

- Telemetry says why a device sends nothing: the local agent reads Telegraf's errors and the API pollers' and shows them per device and kind (nothing listening, no answer, login refused, no route, TLS) with what to check, on Settings > Telemetry and on the agent's page. See `docs/telemetry.md`, "When a device sends nothing".
- **Test now** and **Raw data** per device on Settings > Telemetry: collect from one device once through the agent and see what came back or the exact error, or the last lines Telegraf sent for it.
- Settings > Telemetry shows, per agent, whether Telegraf is posting to it, how many points came in and how often it forwarded them to Floorbit.
- The agent's log says when a device is first heard or comes back, and every five minutes what came in.
- `docs/agent.md` lists every port the agent's plugins listen on, whether it is published by default, and how to check each.

### Changed

- The local agent runs Telegraf itself (it is in the agent image): no telegraf container and no `--profile telemetry` any more. The agent publishes 162/udp and 57000 for traps and MDT by default. Remove an old `telegraf` service and run `docker compose up -d --remove-orphans`; `FLOORBIT_TELEGRAF=sidecar` keeps the old way. See `docs/agent.md`, "Telegraf".
- A plugin's warning on the Local agents page is a translated sentence with a link to what fixes it, where the plugin gives one.

### Fixed

- Telegraf's posts to the agent were dropped (a "broken pipe" in Telegraf's log): Telegraf no longer gzips them on this local hop.
- Settings > Telemetry said "Nothing yet" and 0 ports for every device while a local agent collected: it now shows what the agent heard.
