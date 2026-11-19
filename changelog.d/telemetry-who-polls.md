### Changed

- When LibreNMS runs, it alone polls the switches' ports and walks their ARP and MAC tables. Telemetry no longer polls the same things a second time, and keeps traps, device facts and streams. A new Telemetry setting, "Who polls the switches", can hand everything to Telemetry instead. When one source doesn't know an IP, Floorbit asks the other.
