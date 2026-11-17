### Added

- LAN cache plugin: the local agent reads the lancache.net access log and lancache-dns's query
  log in the hall, checks that the cache answers and that lancache-dns points at it, and watches
  the cache's disk. A new LAN cache page shows what the cache saved, the cache machine's health,
  downloads 5 or more players fetched, files the cache keeps fetching again, and DNS lookups of
  the cached services. Admins can clear the cache when the hall allows it on the agent. Games, the
  stats wall and DNS analytics get the numbers too, also with a hosted Floorbit. Client addresses
  never leave the hall. See docs/lancache.md.
