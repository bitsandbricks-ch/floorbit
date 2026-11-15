### Added

- API tokens: an admin makes tokens for scripts and other tools under Settings > API tokens, each
  with a role, read-only by default and with an optional expiry. Only a fingerprint is kept, and
  changes made with a token are in the audit log. See `docs/api.md`.
- `GET /api/version` and a `Floorbit-API` header on every API answer, with a promise of when the
  version goes up.
