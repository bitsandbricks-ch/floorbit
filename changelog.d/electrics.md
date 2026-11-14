### Added

- Electrics page (`/power`): distribution boards and the circuits they feed (whole seat blocks, single
  rows, switches), with fuse rating and phase. The load is a percentage of the fuse, from readings the
  Electrics team types in or from power plugins (new plugin area `power` for smart PDUs and meters).
- A circuit turns amber at 80 % and red at 95 % (settings `POWER_WARN`, `POWER_CRIT`). Turning red or
  a reported trip opens an incident for the Electrics team naming the seats and switches it feeds,
  posts to Discord (`DISCORD_POWER_ALERTS`) and fires the `power.alert` plugin hook.
- **Power circuits** layer on the floor plan: seats and switches in their circuit's colour, the
  boards where they hang, and a count of red circuits next to Power in the top bar.
- New permission `power.edit` (Admin and Lead). Members of the Electrics team who work incidents
  may enter readings and trips. `POWER_ENABLED` turns the page and the layer off.
- Incidents can be about a power circuit.
