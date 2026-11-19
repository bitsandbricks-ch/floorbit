### Added

- Plugins get a small stable helper module (`floorbit.plugins.helpers`): the port summary, device
  matching, MAC addresses, the uplink pattern and switch lists. Marketplace plugins import these
  instead of Floorbit's internals, so a Floorbit update doesn't break them.
