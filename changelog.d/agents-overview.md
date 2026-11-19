### Changed

- Local agents is now an overview: four figures (online, needing a look, plugins healthy, calls in
  the last hour), then one card per agent with when it was last seen, its version, whether it uses
  the WebSocket or the long poll, how long it has run, its plugins and what needs a look. Failover
  per hall and this Floorbit's own state moved to their own tabs, and enrolling opens from the
  page's button.
- Each agent has its own page (`/settings/agents/<id>`) with tabs for its overview, its plugins,
  its plugin updates and its settings (name, key, halls, plugins it leaves off, revoke).

### Added

- An agent running an older version than another enrolled agent is flagged, next to the older
  agent protocol it already was.
