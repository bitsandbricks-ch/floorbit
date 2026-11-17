### Added

- Device telemetry without LibreNMS: Settings > Telemetry lists the switches, routers and firewalls
  to collect from (SNMP polling and traps, gNMI, Cisco model-driven telemetry, NX-API, RESTCONF,
  the OPNsense API, or a firewall's own Telegraf), and Telegraf (`--profile telemetry`) collects
  for Floorbit or the local agent. The new Telemetry plugin feeds the floor plan, the seat
  inspector, check-in and the topology from it. History in Floorbit's database or, optionally,
  VictoriaMetrics (`--profile metrics`); VictoriaLogs and Grafana as optional profiles. MAC tables
  and ARP are never stored. See `docs/telemetry.md`.
- IP and MAC history (Network > IP and MAC history): where each machine was seen, by IP, MAC,
  switch port and seat, kept for 7 days in Floorbit's database. Search any IP or MAC (also from
  Go to), and open a port's or a seat's history. Fed by telemetry, also through the local agent.
  See `docs/endpoints.md`.
