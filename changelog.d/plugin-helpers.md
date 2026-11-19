### Added

- Plugins get a small stable helper module (`floorbit.plugins.helpers`): the port summary, device
  matching, MAC addresses, the uplink pattern and switch lists. Marketplace plugins import these
  instead of Floorbit's internals, so a Floorbit update doesn't break them.
- Official Marketplace plugins that answer for the hall (monitoring, inventory, DNS, Wi-Fi, ...)
  run on the local agent like the built-in ones, also without an agent part of their own.
