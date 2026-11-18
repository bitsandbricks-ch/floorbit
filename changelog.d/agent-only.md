### Changed

- Floorbit now reaches the event network only through the local agent, also when it runs in the hall:
  monitoring, NetBox, health checks, DNS, Wi-Fi, power meters, switch logins and syslog all go
  through it, and the server refuses to call those plugins itself. Run the agent next to Floorbit
  (the compose file does). Without a connected agent, pages show the last known state and say so.
  `LAN_ACCESS=direct` brings the old behaviour back for development.
- `docker-compose.yml` and the Kubernetes manifest start the agent next to Floorbit, and it enrols
  itself through a shared key file (`FLOORBIT_LOCAL_AGENT_KEY_FILE`): no key to copy. Syslog
  (udp/514) and NetFlow (udp/2055) now go to the agent container; the separate `flows` profile is
  gone, and Telegraf (`telemetry` profile) runs next to the agent.
