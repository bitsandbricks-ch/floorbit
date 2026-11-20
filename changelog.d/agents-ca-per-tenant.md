### Fixed

- The agents' certificate authority belongs to the tenant, not to one event: making a later event
  live no longer makes a new CA, so crew devices that installed it keep trusting the agents. At
  start, Floorbit moves the live event's CA to the tenant.
