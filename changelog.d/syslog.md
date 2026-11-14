### Added

- Logs: a syslog receiver (UDP, optionally TCP, RFC 3164 and RFC 5424) for switches, firewalls and
  DHCP servers, with a Logs page to search by words, device, seat, port and level and to follow
  along live. Lines that name a switch port show the seat on it. Off until `SYSLOG_ENABLED`; only
  allowed senders, a rate cap per sender, and kept for 24 hours. Needs `seats.view`. See
  `docs/syslog.md`.
