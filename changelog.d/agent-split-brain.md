### Added

- Two agents in one hall that can't hear each other's VRRP (split brain) no longer both poll the
  devices and try the logins: Floorbit tells all but one to stand by until they hear each other
  again. Needs the matching floorbit-agent.
