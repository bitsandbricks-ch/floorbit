### Added

- Platform admins: only accounts of the default tenant with the platform admin flag see
  Settings > Tenants and can visit other tenants. The first account gets the flag; admins give it
  on Settings > Users or with `flask platform-admins add`. On the upgrade every admin of the default
  tenant keeps it.
- Platform admins can set a tenant's admin from Settings > Tenants, for a tenant that is locked out.
- A tenant's admins can turn platform visits off on Settings > Users (on by default).
