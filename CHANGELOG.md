# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). `mason bump` turns `[Unreleased]` into the new version.

## [Unreleased]

### Added

- Seat inspector: a "Switch port" section with the port's state, link speed and duplex, download and
  upload, errors, load, a refresh button and a link to the port in LibreNMS.
- GitLab pipeline: ruff, JavaScript syntax check, pytest smoke tests, MR screenshots, Docker image
  build and push, and a release job for `v*` tags.
- Repo conventions from the BitsAndBricks repo template: README, AGPL-3.0 licence, AGENTS.md,
  CONTRIBUTING.md, SECURITY.md, `.mason.toml`, `.editorconfig`, CODEOWNERS, merge request and issue
  templates.
