### Changed

- Every Floorbit now serves a tenant: a self-hosted install is the `default` tenant of its own
  platform and runs the same code as a hosted one. Nothing moves on the upgrade and nothing about
  tenants shows until a second one exists. The Redis (Valkey) keys get the tenant's name in front,
  so the cache fills again once after the upgrade.
