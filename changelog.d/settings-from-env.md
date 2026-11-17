### Added

- The Settings page now has the operational settings that were only environment variables until
  now: port trouble, logs (allowed senders, rate, retention), DNS, LAN cache and bandwidth forecast,
  game server and service checks, switch config backups and the switch terminal, check-in PIN tries,
  the seat source's TLS check and the find-your-seat page. A value saved there wins over the env var;
  an existing `.env` keeps working unchanged. Database, Redis, keys, time zone and the hosted-server
  limits stay in the environment (docs/integrations.md).
