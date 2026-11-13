# Contributing to Floorbit

Thanks for helping! A short issue or pull request is always welcome: bug reports, ideas, docs
fixes and code.

## Before you start

- **Bugs and ideas:** open an issue with the **Bug** or **Feature** template first, so we can agree
  on the approach before you spend time on code.
- **Security problems:** please don't open a public issue. See [SECURITY.md](SECURITY.md).

## Making changes

1. Make a branch from `master` and keep one topic per pull request.
2. Run the checks from the README's [Develop](README.md#develop) section before you push.
3. Add a line under `## [Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for anything users notice.
4. Open the pull request as a **draft** and fill in the template. Every pull request has
   **screenshots** (the CI `screenshots` job takes them). CI must be green before it can be
   merged.

## Code style

- Python: [ruff](https://docs.astral.sh/ruff/) with the settings in `pyproject.toml`, 4 spaces.
- JavaScript and CSS: plain browser code, no build step, 2 spaces.
- [`.editorconfig`](.editorconfig) sets indentation and line endings for your editor.
- Short comments that explain why, not what.

Coding agents: [AGENTS.md](AGENTS.md) has the rules you follow.

## Licence

By contributing you agree that your contribution is released under this project's
[licence](LICENSE) (AGPL-3.0).
