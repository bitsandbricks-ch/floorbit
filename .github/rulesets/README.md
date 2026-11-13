# Rulesets

`mason doctor --fix` imports these (they must match what is live on GitHub). By hand: Settings ›
Rules › Rulesets › New ruleset › Import a ruleset.

| File | What it does |
| --- | --- |
| `main.json` | The default branch takes pull requests only, no force-push, no deletion. **CI passed** must be green. Repo admins may merge their own pull request without an approval (one maintainer), but nobody pushes to `master` directly. |
| `tags.json` | Only repo admins create `v*` tags (a release); nobody moves or deletes one. |

**CI passed** is the last job of `.github/workflows/ci.yml`. It waits for every other job, so a
repo can add or skip jobs without touching the ruleset.
