# Floorbit frontend

The React app: React 19, TypeScript, [Mantine](https://mantine.dev), TanStack Query and
react-router, built with Vite. It is set up like Hubra's `app/frontend` (by Mike), and some
pieces come from there (marked in the files). Flask stays the API and serves the pages; see
[docs/architecture.md](../docs/architecture.md#react-app-frontend).

## Develop

```sh
cd frontend
npm ci              # Node 24 / npm 11 (the lock file needs npm 11)
npm run dev          # http://localhost:5173, API and sign-in proxied to Flask on :5000
```

Start Flask as usual (`python app.py`) next to it. Set `FLOORBIT_URL` if Flask runs elsewhere.
Sign in on `http://localhost:5173/login`: the proxy passes the session cookie through.

## The shared packages

`@bitsandbricks/tokens`, `ui` and `widgets` (bitsandbricks-ch/ui) are pinned to a **dev build**,
not a release: ui publishes one under the npm tag `dev` for every commit to its main, and Floorbit
follows them for now. Every hour `.github/workflows/ui-dev.yml` opens or updates one pull request
(`bot/ui-dev`) that moves the three to the newest one, with CI run on it. To take a ui change at
once, run that workflow by hand, or `npm install --save-exact @bitsandbricks/ui@dev` (and tokens
and widgets) on your branch.

## Check, like CI

```sh
npm run lint
npm run typecheck
npm test
npm run build        # writes ../static/app/, which Flask serves
```

## Rules

- A page is a file in `src/pages/` and a route in `src/routes/<area>.ts` (a new area is a new file there; `App.tsx` collects them). Point its Flask route at
  `spa.render('<Title>')` (`floorbit/spa.py`), so Flask still checks sign-in and roles. A page
  outside the app shell (`shell: false`) uses `spa.render('<Title>', shell=False)`: it then loads
  without the shell and with only the texts in `src/i18n/englishCore.ts` (issue #1293). A new
  feature file it needs goes into that list and the three lists beside it (the i18n test checks).
  It also gets only the Mantine styles listed in `src/styles/mantinePublic.ts`. When it uses
  another Mantine component, `npm run build` fails and prints the list to paste. A new page of
  this kind also goes into `PUBLIC_PAGES` in `vite.mantine.ts`.
- A page's sidebar row, its tabs and their icons live in `src/nav/areas/<area>.ts` (one file per
  row); `src/nav/sections.ts` only sorts the rows into groups.
- Every text goes through `t()` with a key in `src/i18n/en/<feature>.json` **and**
  `src/i18n/de-CH/<feature>.json` (Swiss spelling, no "ß"). The i18n test fails otherwise.
- Colours come from the shared design tokens (`var(--bnb-...)`), never hex values, so themes work.
  Only `src/styles/bnb.css` reads the old `--color-*` names (`src/tokens.test.ts` checks).
- Text from the API or a plugin is shown as text. No `dangerouslySetInnerHTML` (ESLint refuses it).
- Query keys come from `src/api/keys.ts`.
- Use the shared pieces from `@bitsandbricks/ui` and `@bitsandbricks/widgets`. ESLint refuses
  imports of the Floorbit copies they replaced (`DataTable`, `PageHead`, `SidePanel`, ...).
- Added a translation file and the tests don't see it? Vitest caches transforms: delete
  `node_modules/.vitest-cache`.
