### Changed

- LibreNMS is now a built-in plugin, the monitoring source for live status, ports, the seat
  heatmap, the status monitor and the check-in page. It is on by default and keeps the existing
  LibreNMS settings and `LIBRENMS_*` variables, so nothing changes for a running install. An admin
  can turn it off under Settings > Plugins; the floor plan then shows switches as unknown.
- The status monitor and the check-in page no longer call LibreNMS themselves: everything goes
  through the monitoring plugin.

### Added

- Plugins can be the monitoring source with `uses: [monitoring]` (see `docs/plugins.md`).
