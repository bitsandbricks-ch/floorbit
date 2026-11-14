### Added

- Service health wall (`/health`): DHCP, DNS, the LAN cache, game servers and the internet uplink,
  green, amber or red, grouped by kind. `?screen=1` is the big-screen version for kiosk and ops
  screens. Each service comes from a plugin with the new `health` area; the built-in HTTP check and
  the demo data feed it. See `docs/health.md`.
- Discord posts when a service on the health wall goes red (confirmed over two checks) and when it
  is back. Plugins can hook `health.status`.
