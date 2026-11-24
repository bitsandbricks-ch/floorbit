### Changed

- A device's feature switches list only what fits its kind (port actions on switches, the terminal
  and commands on switches, routers and firewalls, a plugin on the roles it names); the rest fold
  under Other features. Plugins that don't work per device are no longer listed.

### Added

- Plugin manifests can name the device roles an agent part works on: `agent.targets.roles`.
