### Fixed

- A switch name from the inventory finds that LibreNMS device, not another one whose name starts the
  same (`sw-a1` and `sw-a10`): the same display name, hostname or sysName first, then the short name,
  then a partial name only when one device has it.
- Looking up which port an IP is on keeps working when Redis fails or holds a garbled entry.
- IPs, MACs and device names go into LibreNMS URLs as one path segment each.
