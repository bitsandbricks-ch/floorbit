### Added

- A built-in Grafana Loki plugin keeps the syslog longer: every line is pushed to Loki with a few
  labels, and the Logs page searches it with LogQL. Other plugins can do the same through the new
  `logs` area. See `docs/plugins.md` and `docs/syslog.md`.
