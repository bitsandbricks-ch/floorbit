# Rules for coding agents

These rules are for AI coding agents (Claude Code, Codex, Copilot, ...) working on Floorbit.
Humans: see [CONTRIBUTING.md](CONTRIBUTING.md); the same rules apply to you in spirit.
`CLAUDE.md` imports this file.

## What this is

A Flask web app that shows the event's network on a floor plan: switches from NetBox, their live
status and ports from LibreNMS, seat blocks, and which switch port each seat is on. Overview for
users: [README.md](README.md).

| Path | What lives there |
| --- | --- |
| `app.py` | Entry point only: `app = create_app()`. |
| `floorbit/` | The Flask app. `blueprints/` has one module per area of the API; `sources/` is the only code that talks to NetBox and LibreNMS. See `docs/architecture.md`. |
| `integrations/` | Live updates, status monitor, Discord, seat sources, check-in. See `docs/integrations.md`. |
| `auth/` | Sign-in: accounts in `data.json`, the request guard, login providers. See `docs/auth.md`. |
| `templates/` | Jinja pages. |
| `static/js/`, `static/css/` | The browser app (plain JavaScript and CSS, no build step). The editor is split by feature in `static/js/editor/` (load order in its README). |
| `changelog.d/` | Changelog fragments, one per pull request. |
| `seats.json` | Seat number to IP and username. |
| `tests/` | pytest smoke tests against the Flask test client, with a fake Redis. |
| `scripts/screenshots.py` | Takes the pull request screenshots (the `screenshots` CI job runs it). |
| `.github/workflows/` | GitHub Actions: `ci.yml` (lint, test, screenshots, the `CI passed` gate), `image.yml` (GHCR), `release.yml`. |
| `.claude/`, `.planning/` | GSD workflow files. Leave them alone unless the task is about them. |

## Workflow

1. **Branch:** work on your own branch, never push to `master`. One topic per branch and pull request.
2. **Before you push**, run what CI runs and make it pass locally:
   - `pip install -r requirements.txt -r requirements-dev.txt`
   - `ruff check .`
   - `pytest -q`
   - `find static -name '*.js' -exec node --check {} \;`
   - `docker build .`
3. **Pull request:** open it as a **draft** and fill in the template
   (`.github/pull_request_template.md`). Link the issue.
4. **Screenshots:** every pull request has them, UI change or not. Take them from the CI
   `screenshots` job's artifact (or run `scripts/screenshots.py` against a local server) and put them in the
   description.
5. **CI:** wait for the checks. Fix failures yourself. Never skip, disable or weaken a check or a
   test to get green.
6. **Done** means the task is complete, the checklist is ticked and CI is green: then mark
   the pull request ready. Leave it a draft only while work is open or you are blocked, and say why
   in the description.
7. **Never merge** your own pull request, never force-push to a branch someone else works on, and
   never push a tag. Merging and releasing are the maintainer's call.
8. Keep the pull request description current when you push more commits.

## Rules

- **Ask, don't guess.** Never make up facts about the project, its users or its author (features,
  history, numbers, names). Leave a `TODO` and ask instead.
- **No secrets** in code, commits, screenshots, logs or docs. Use example values (`example.com`).
  Real seat names, usernames and IPs are personal data: keep them out of screenshots and fixtures.
- **Names:** the brand is written "BitsAndBricks". Public text names the author as "Mike" only.
- **Releases:** don't edit `VERSION` or the changelog headings by hand; `mason bump` does that.
  Describe your change in a new `changelog.d/<topic>.md` fragment, not in `CHANGELOG.md`
  (see `changelog.d/README.md`).
- **Tests never talk to NetBox, LibreNMS or a real Redis:** they use the fakes in `tests/conftest.py`.
  Keep it that way.
- **User to IP mapping** goes through providers that can be swapped. Don't integrate the Lock and
  Load backend yet: it gets a major rework in 2027.
- **CI images:** pin them to a version tag (`python:3.11-slim`, not `python:latest`), and pass
  `${{ github.* }}` text that users control (branch names, PR titles) through `env:`, never pasted into
  a `run:` script. Pin actions to a major version tag (`actions/checkout@v4`).
- **Dependencies:** add one only when it clearly pays for itself, and say why in the pull request.
- **Where code goes:** a new API area is a new blueprint in `floorbit/blueprints/`; a new editor
  feature is a new file in `static/js/editor/`. NetBox and LibreNMS calls go through
  `floorbit.sources`, never straight from a blueprint. Nothing names one particular event:
  event names, branding and hosts are settings.
- Write short comments that explain why, not what.
- Stay inside the repository. Ask before deleting files you didn't create.
