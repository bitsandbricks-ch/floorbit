# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). `mason bump` turns `[Unreleased]` into the new version.

## [Unreleased]

### Added

- Kiosk view at `/kiosk`: a read-only floor plan for a big screen with switch status, seat
  occupancy and a list of switches that are down. Uses live updates when the server has them and
  polls otherwise. See `docs/kiosk.md`.
- GitLab pipeline: ruff, JavaScript syntax check, pytest smoke tests, MR screenshots, Docker image
  build and push, and a release job for `v*` tags.
- Repo conventions from the BitsAndBricks repo template: README, AGPL-3.0 licence, AGENTS.md,
  CONTRIBUTING.md, SECURITY.md, `.mason.toml`, `.editorconfig`, CODEOWNERS, merge request and issue
  templates.

### Changed

- ruff checks a wider rule set (pycodestyle, import order, pyupgrade, bugbear, blind except,
  comprehensions, simplify, ruff-specific), and the code is cleaned up to pass it. Redis errors are
  now caught as `redis.RedisError` instead of any `Exception`.

### Fixed

- The MR screenshots job waits for page load instead of network idle, which never came once the
  live-updates stream (`/api/events`) was open.
