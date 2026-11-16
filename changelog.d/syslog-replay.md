### Added

- Syslog an agent kept on disk while the uplink was down lands at its own time (back to the retention limit), raises no stale log alerts, and has its own rate cap. A line two agents both sent, or a batch sent twice, is kept once.
