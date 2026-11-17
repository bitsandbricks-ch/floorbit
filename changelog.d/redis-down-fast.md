### Fixed

- Without Redis (or while it is down), every request waited about half a minute: before each request
  Floorbit retried Redis five times with sleeps, and the Redis library added its own. Now a missing
  Redis is tried at most once every 15 seconds, in under a second, and pages answer straight away.
- Clearing the cache (`POST /api/cache/invalid`) also forgets where IPs were last seen, so a seat moved
  to another port shows up right away; clearing one switch forgets only what was seen on it. A bad
  `hostnames` list is refused (400) instead of failing.
- The NetFlow collector reconnects to Redis by itself (it may start before Redis) and keeps running
  when Redis goes away for a moment, instead of stopping.
