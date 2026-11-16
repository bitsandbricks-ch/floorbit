### Changed

- The seat mapping is keyed by switch port: each seat says which switch and port it is on, from a cable, a check-in or a hand entry. The IP and MAC are read off that port from the switches' MAC tables; one typed in or imported only counts while the port isn't known. Port actions use the mapped port first.
- The seat mapping CSV has `switch` and `port` columns. Older files without them still import.

### Added

- "Find the port by MAC" in the seat mapping form looks up where a machine is plugged in and fills the switch and port; it can be changed again.
- Hand entries from before have a one-click "Find the ports" that gives each the port its IP or MAC is seen on.
