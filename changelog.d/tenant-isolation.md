### Security

- Tenants that share a `SECRET_KEY` no longer accept each other's sign-in cookies or seat help
  links, and tenants that share an S3 bucket keep their backups in separate folders.

### Fixed

- `MONITORING_CACHE_FILE` is kept per tenant and event like the other configured files.
