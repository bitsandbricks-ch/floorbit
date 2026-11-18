### Fixed

- A burst of changes no longer starts a thread for every plugin hook: hooks run on a few shared
  threads, and when too many wait, the oldest are dropped and the plugin's log says so. Hooks now
  run in the event the change happened in.
- A plugin tile or endpoint that hangs answers with an error after 10 seconds instead of holding
  the page, and one stuck plugin can't take up every worker.
- An instance that couldn't download a Marketplace plugin (index or GitHub away) tries again on
  its own instead of waiting for the next install.
- With a database, checking which plugins are on no longer asks the database again and again
  for every request.

- A plugin that calls `sys.exit()`, or whose `plugin.py` never finishes loading, no longer stops
  a worker or Floorbit's start: it shows an error on its page instead.
- Two hooks of one plugin saving different keys of its state at the same time no longer undo each
  other.
- While a Marketplace source is away (a GitHub outage), its last good index is used for up to a
  day instead of the Marketplace going empty.

- With two agents in one hall, a plugin action (clearing the LAN cache, ...) runs once, on the
  hall's primary agent, instead of on both.

### Security

- Marketplace indexes and plugin bundles are read with a size cap before they are in memory.
- An index older than one the server already read is refused even when its signature checks out,
  so serving an old copy can't hide a withdrawn version.
- A `plugin.yaml` over 256 KB is refused unread.
