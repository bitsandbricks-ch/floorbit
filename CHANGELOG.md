# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). `mason bump` turns `[Unreleased]` into the new version.

## [Unreleased]

### Added

- Floor plan grid that follows pan and zoom and lines up with the snap step (Layers > Grid).
- Traffic heatmap layer with a Seats / Switches / Both level, coloured by LibreNMS throughput on a
  log scale. Switches show as cards with their name and throughput. Replaces the separate switch
  and seat heatmap toggles. Seat lookups for it now run in parallel.
- Kiosk view at `/kiosk`: a read-only floor plan for a big screen with switch status, seat
  occupancy and a list of switches that are down. Uses live updates when the server has them and
  polls otherwise. See `docs/kiosk.md`.
- GitLab pipeline: ruff, JavaScript syntax check, pytest smoke tests, MR screenshots, Docker image
  build and push, and a release job for `v*` tags.
- Sign-in in front of the editor and the settings page: username and password accounts (scrypt
  hashed, kept in `data.json`), `flask users` commands, sessions, lockout after repeated failures.
  Read-only API, the check-in page and the kiosk view stay open. Built to take SSO (OIDC) or
  Discord sign-in as a provider later.
- Roles (viewer, editor, admin) and a Users page in the settings where admins add accounts, change
  roles, reset passwords and remove accounts. Check-in records need an editor, integration
  controls an admin.
- Repo conventions from the BitsAndBricks repo template: README, AGPL-3.0 licence, AGENTS.md,
  CONTRIBUTING.md, SECURITY.md, `.mason.toml`, `.editorconfig`, CODEOWNERS, merge request and issue
  templates.
- Seat inspector: a "Switch port" section with the port's state, link speed and duplex, download and
  upload, errors, load, a refresh button and a link to the port in LibreNMS.

### Changed

- The project moved from GitLab to GitHub (`bitsandbricks-ch/floorbit`). CI runs on GitHub Actions
  with the same jobs, and the Docker image is published to `ghcr.io/bitsandbricks-ch/floorbit`.
- ruff checks a wider rule set (pycodestyle, import order, pyupgrade, bugbear, blind except,
  comprehensions, simplify, ruff-specific), and the code is cleaned up to pass it. Redis errors are
  now caught as `redis.RedisError` instead of any `Exception`.

### Fixed

- Seat inspector: download and upload were swapped (LibreNMS counts from the switch's side).
- The MR screenshots job waits for page load instead of network idle, which never came once the
  live-updates stream (`/api/events`) was open.
