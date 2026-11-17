### Added

- Device telemetry without LibreNMS: Settings > Telemetry lists the switches, routers and firewalls
  to collect from (SNMP polling and traps, gNMI, Cisco model-driven telemetry, NX-API, RESTCONF,
  the OPNsense API, or a firewall's own Telegraf), and Telegraf (`--profile telemetry`) collects
  for Floorbit or the local agent. The new Telemetry plugin feeds the floor plan, the seat
  inspector, check-in and the topology from it. History in Floorbit's database or, optionally,
  VictoriaMetrics (`--profile metrics`); VictoriaLogs and Grafana as optional profiles. MAC tables
  and ARP are never stored. See `docs/telemetry.md`.
