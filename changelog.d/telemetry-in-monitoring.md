### Changed

- Telemetry moved from Settings to **Monitoring > Telemetry**, at `/telemetry`, and the crew can read it: each device's last word, its problems, its agent and what came in. Test now, Raw data, Device setup and the ingest token stay with admins.
- Telemetry devices are set up only in the inventory: turn on the Telemetry feature for a device, a tag, a group or a type, with its logins stored there. The separate device list and form on the old page are gone, with their API (`/api/settings/telemetry/targets`). A device that only sends by itself (a firewall's own Telegraf, MDT, traps) needs no login.
- The telemetry API moved from `/api/settings/telemetry/*` to `/api/telemetry/*` (`overview`, `devices`, `test`, `raw`, `device-config?name=`, `token`, `telegraf.conf`).
- Demo data: the demo's switches and firewalls are set up for telemetry through two inventory groups, Network and Firewalls.
