### Added

- Discovery is split into actions per kind of device (identity, interfaces, VLANs and networks,
  transceivers, PoE, routes), each on its own schedule: model and optics hourly, the rest every
  discovery interval. Admins change an action's interval, and any editor runs one action or all of
  them now, for every device or a single one.
