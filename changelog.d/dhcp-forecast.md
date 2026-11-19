### Added

- DHCP scopes that fill up fast warn before they are full: the service health tile says "Full in about 25 minutes" from the last quarter of an hour, and a scope forecast full within the hour shows amber on the wall and in Problems. Plugins report a pool's size with the new optional `capacity` on a health check.

### Fixed

- Problems and the shift handover link a service to the Services page; the old service health page is gone, so the link led nowhere.
