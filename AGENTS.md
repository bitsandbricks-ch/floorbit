# Rules for coding agents

These rules are for AI coding agents (Claude Code, Codex, Copilot, ...) working on Floorbit.
Humans: see [CONTRIBUTING.md](CONTRIBUTING.md); the same rules apply to you in spirit.
`CLAUDE.md` imports this file.

## What this is

A Flask web app that shows the event's network on a floor plan: switches from NetBox, their live
status and ports from LibreNMS, seat blocks, and which switch port each seat is on. Overview for
users: [README.md](README.md).

The standing product decisions (scope, architecture, modularity, UI rules, privacy, process) are in
[docs/product-spec.md](docs/product-spec.md). Follow them; a change to one updates that page in the same
pull request.

| Path | What lives there |
| --- | --- |
| `app.py` | Entry point only: `app = create_app()`. |
| `floorbit/` | The Flask app. `blueprints/` has one module per area of the API; `builtin_plugins/` has NetBox (feeds the inventory) and LibreNMS (monitoring, asked through `sources.monitoring()`). See `docs/architecture.md`. |
| `integrations/` | Live updates, status monitor, Discord, seat sources, check-in. See `docs/integrations.md`. |
| `auth/` | Sign-in: accounts in `data.json`, the request guard, login providers. See `docs/auth.md`. |
| `frontend/` | The React app (React, TypeScript, Mantine, TanStack Query, Vite), set up like Hubra's. Pages move into it one at a time; Flask serves it through `templates/spa.html` (`floorbit/spa.py`). See `frontend/README.md`. |
| `templates/` | `spa.html` (the React app's page), the sidebar's first paint, and the database-down page. |
| `static/js/`, `static/css/` | Small shared scripts and styles outside the React build (theme, notifications, attribution). |
| `changelog.d/` | Changelog fragments, one per pull request. |
| `seats.json` | Seat number to IP and username. |
| `tests/` | pytest smoke tests against the Flask test client, with a fake Redis. |
| `scripts/screenshots.py` | Takes the pull request screenshots (the `screenshots` CI job runs it). |
| `.github/workflows/` | GitHub Actions: `ci.yml` (lint, test, screenshots, the `CI passed` gate), `image.yml` (GHCR), `release.yml`. |
| `.claude/`, `.planning/` | GSD workflow files. Leave them alone unless the task is about them. |

## Workflow

1. **Branch:** work on your own branch, never push to `master`. One topic per branch and pull request.
   Run `scripts/setup-git.sh` once per clone: it sets up the merge driver that merges translation
   files by key (see [Merge conflicts](#merge-conflicts)).
2. **Before you push**, run what CI runs and make it pass locally:
   - `pip install -r requirements.txt -r requirements-dev.txt`
   - `ruff check .`
   - `pytest -q` (the agent tests need bitsandbricks-ch/floorbit-agent cloned next to this repository,
     at the commit in `AGENT_REF`, or `FLOORBIT_AGENT_SRC` pointing at it)
   - `find static -path static/app -prune -o -name '*.js' -exec node --check {} \;`
   - in `frontend/`: `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`
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
9. **Keep it mergeable:** when `master` moves while your pull request is open, merge `master` into
   your branch (no rebase, no force-push), resolve, run again what the conflict touched and push.

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
- **Where code goes:** a new API area is a new blueprint in `floorbit/blueprints/`; a new page is a React page in
  `frontend/src/pages/` with its texts in English and German (`frontend/src/i18n/`); a new editor
  feature is a new file in `frontend/src/pages/plan/edit/`. A new error message from the server gets its German text
  in `floorbit/locales/de-CH/<area>.json` (`tests/test_i18n_server.py` checks). NetBox and LibreNMS calls live in their
  plugins; the core asks the inventory and `floorbit.sources.monitoring()`, never the API itself. Nothing names one particular event:
  event names, branding and hosts are settings.
- Write short comments that explain why, not what.
- Stay inside the repository. Ask before deleting files you didn't create.

## Merge conflicts

Many pull requests are open at once, so a line every pull request edits is a conflict waiting to
happen. Add files, don't grow shared ones:

| Instead of | Do this |
| --- | --- |
| one big translation file (`floorbit/locales/de-CH.json` is gone; `discord.de-CH.json` too should not grow) | add to `floorbit/locales/de-CH/<area>.json` (`log.de-CH/`, `discord.de-CH/`), named after the module that sends the text |
| adding a blueprint to `ALL` in `floorbit/blueprints/__init__.py` | nothing: a module in `floorbit/blueprints/` with a `bp` registers itself |
| adding a new area's types to `frontend/src/api/types.ts` | put them in `frontend/src/api/<area>.ts`, next to its queries (like `tenantEvents.ts`) |
| adding a new page's styles to `frontend/src/app.css` or `frontend/src/styles/` | a `<Page>.css` next to the page, imported by it |
| one big test file for an area (`tests/test_cables.py`) | a new `tests/test_<area>_<topic>.py` for a new topic |
| editing `docs/api-reference.md` by hand, or merging its conflict | run `python scripts/api_reference.py` after the merge; it writes the file from the routes |
| a branch based on another open pull request | a branch from `master`; if it needs the other one, wait for it |

Two threads (or people) never work on the same page or area at the same time. When a conflict comes
anyway: merge `master` in, resolve it yourself, never by taking one side wholesale for a file both
sides changed.
